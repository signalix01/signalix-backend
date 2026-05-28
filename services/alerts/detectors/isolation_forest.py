"""
Isolation Forest Anomaly Detector

Implements ML-based anomaly detection using Isolation Forest algorithm.
Requirements: 11.4, 16.7

Algorithm:
- Isolation Forest isolates anomalies by randomly selecting features and split values
- Anomalies are easier to isolate (require fewer splits) than normal points
- Uses ensemble of isolation trees for robust detection
- Contamination parameter: 0.02 (2% expected anomaly rate)

Training:
- Trained daily on 90-day rolling window of OHLCV feature vectors
- Feature vector: [price_change_pct, volume_ratio, atr_change_pct, high_low_range, close_position_in_range]
- Models stored in Redis with 48h TTL by instrument

Detects:
- Complex multi-dimensional anomalies not captured by univariate methods
- Unusual combinations of price, volume, and volatility patterns
- Subtle market microstructure anomalies
"""

import numpy as np
import pandas as pd
import pickle
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import redis
from sklearn.ensemble import IsolationForest

from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity
from shared.config.settings import settings


class IsolationForestDetector:
    """
    Isolation Forest ML-based anomaly detector for multi-dimensional market data.
    
    Uses scikit-learn's IsolationForest to detect complex anomalies that
    univariate methods (Z-score, CUSUM) might miss.
    
    Features:
    - Multi-dimensional feature space (price, volume, volatility)
    - Automatic model training on historical data
    - Redis-based model caching with TTL
    - Real-time detection on streaming data
    """
    
    def __init__(self, contamination: float = 0.02, n_estimators: int = 100,
                 max_samples: int = 256, random_state: int = 42):
        """
        Initialize the Isolation Forest detector.
        
        Args:
            contamination: Expected proportion of anomalies (default: 0.02 = 2%)
            n_estimators: Number of isolation trees (default: 100)
            max_samples: Number of samples to draw for each tree (default: 256)
            random_state: Random seed for reproducibility (default: 42)
        """
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state
        
        # Redis connection for model storage
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
        self.model_ttl = 48 * 3600  # 48 hours in seconds
    
    def _compute_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute feature vector for Isolation Forest.
        
        Feature vector includes:
        1. price_change_pct: Percentage change in close price
        2. volume_ratio: Current volume / 20-day average volume
        3. atr_change_pct: Percentage change in ATR (volatility)
        4. high_low_range: (high - low) / close (intraday range)
        5. close_position_in_range: (close - low) / (high - low) (where close is in the range)
        
        Args:
            data: DataFrame with columns: open, high, low, close, volume
        
        Returns:
            DataFrame with computed features
        """
        df = data.copy()
        
        # 1. Price change percentage
        df['price_change_pct'] = df['close'].pct_change() * 100
        
        # 2. Volume ratio (current volume / 20-day average)
        df['volume_ma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_20']
        
        # 3. ATR (Average True Range) for volatility
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=14, min_periods=1).mean()
        df['atr_change_pct'] = df['atr'].pct_change() * 100
        
        # 4. High-low range as percentage of close
        df['high_low_range'] = ((df['high'] - df['low']) / df['close']) * 100
        
        # 5. Close position in range (0 = at low, 1 = at high)
        range_size = df['high'] - df['low']
        # Handle zero range (high == low)
        df['close_position_in_range'] = np.where(
            range_size > 0,
            (df['close'] - df['low']) / range_size,
            0.5  # Default to middle if no range
        )
        
        # Select only the feature columns
        feature_cols = [
            'price_change_pct',
            'volume_ratio',
            'atr_change_pct',
            'high_low_range',
            'close_position_in_range'
        ]
        
        # Drop rows with NaN values (from pct_change and rolling windows)
        features = df[feature_cols].replace([np.inf, -np.inf], np.nan).dropna()
        
        return features
    
    def train(self, data: pd.DataFrame, instrument: str) -> IsolationForest:
        """
        Train Isolation Forest model on historical data.
        
        Args:
            data: DataFrame with OHLCV data (minimum 90 days recommended)
                  Required columns: open, high, low, close, volume
            instrument: Instrument symbol (used for model caching)
        
        Returns:
            Trained IsolationForest model
        
        Raises:
            ValueError: If data has insufficient rows or missing columns
        """
        # Validate input data
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        if len(data) < 30:
            raise ValueError(f"Insufficient data for training: {len(data)} rows (minimum 30 required)")
        
        # Compute features
        features = self._compute_features(data)
        
        if len(features) < 20:
            raise ValueError(
                f"Insufficient valid feature rows after computation: {len(features)} "
                f"(minimum 20 required, started with {len(data)} rows)"
            )
        
        # Train Isolation Forest
        model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            max_samples=min(self.max_samples, len(features)),
            random_state=self.random_state,
            n_jobs=-1  # Use all CPU cores
        )
        
        model.fit(features.values)
        
        # Store model in Redis with TTL
        self._store_model(instrument, model)
        
        return model
    
    def _store_model(self, instrument: str, model: IsolationForest) -> None:
        """
        Store trained model in Redis with TTL.
        
        Args:
            instrument: Instrument symbol
            model: Trained IsolationForest model
        """
        model_key = f"iforest_model:{instrument}"
        model_bytes = pickle.dumps(model)
        self.redis_client.setex(model_key, self.model_ttl, model_bytes)
    
    def _load_model(self, instrument: str) -> Optional[IsolationForest]:
        """
        Load trained model from Redis.
        
        Args:
            instrument: Instrument symbol
        
        Returns:
            Trained IsolationForest model or None if not found
        """
        model_key = f"iforest_model:{instrument}"
        model_bytes = self.redis_client.get(model_key)
        
        if model_bytes is None:
            return None
        
        return pickle.loads(model_bytes)
    
    def detect(self, bar: pd.Series, instrument: str = "UNKNOWN",
               asset_class: str = "equity", exchange: Optional[str] = None,
               historical_data: Optional[pd.DataFrame] = None) -> Optional[AnomalyEvent]:
        """
        Detect anomaly in a single bar (real-time detection).
        
        Args:
            bar: Series with OHLCV data for current bar
                 Required keys: open, high, low, close, volume, timestamp
            instrument: Instrument symbol
            asset_class: Asset class
            exchange: Exchange name
            historical_data: Optional DataFrame with recent historical data (for feature computation)
                           If not provided, will attempt to load model from Redis
        
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        
        Raises:
            ValueError: If model not found and historical_data not provided
        """
        # Load or train model
        model = self._load_model(instrument)
        
        if model is None:
            if historical_data is None:
                raise ValueError(
                    f"No trained model found for {instrument} and no historical_data provided. "
                    f"Train a model first using train() method."
                )
            # Train model on historical data
            model = self.train(historical_data, instrument)
        
        # Prepare data for feature computation
        # We need historical context to compute rolling features
        if historical_data is not None:
            # Append current bar to historical data
            data = pd.concat([historical_data, bar.to_frame().T], ignore_index=True)
        else:
            # Only current bar - limited feature computation
            data = bar.to_frame().T
        
        # Compute features
        features = self._compute_features(data)
        
        if len(features) == 0:
            # Cannot compute features (insufficient data)
            return None
        
        # Get features for the last bar (current bar)
        current_features = features.iloc[-1:].values
        
        # Predict anomaly score
        # Returns -1 for anomalies, 1 for normal points
        prediction = model.predict(current_features)[0]
        
        # Get anomaly score (lower = more anomalous)
        # Score is the negative of the average anomaly score of the trees
        anomaly_score = model.score_samples(current_features)[0]
        
        if prediction == -1:
            # Anomaly detected
            
            # Determine severity based on anomaly score
            # More negative score = more anomalous
            if anomaly_score < -0.5:
                severity = AnomalySeverity.CRITICAL
            elif anomaly_score < -0.3:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM
            
            # Parse timestamp
            try:
                if 'timestamp' in bar.index:
                    detected_at = pd.to_datetime(bar['timestamp'])
                    if detected_at.tzinfo is None:
                        detected_at = detected_at.tz_localize('UTC')
                else:
                    detected_at = datetime.utcnow()
            except (ValueError, AttributeError, KeyError):
                detected_at = datetime.utcnow()
            
            # Build description
            feature_values = features.iloc[-1].to_dict()
            description = (
                f"Isolation Forest anomaly detected: unusual multi-dimensional pattern. "
                f"Anomaly score: {anomaly_score:.3f}. "
                f"Features: price_change={feature_values.get('price_change_pct', 0):.2f}%, "
                f"volume_ratio={feature_values.get('volume_ratio', 0):.2f}x, "
                f"atr_change={feature_values.get('atr_change_pct', 0):.2f}%, "
                f"high_low_range={feature_values.get('high_low_range', 0):.2f}%, "
                f"close_position={feature_values.get('close_position_in_range', 0):.2f}"
            )
            
            # Create anomaly event
            anomaly = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=instrument,
                asset_class=asset_class,
                exchange=exchange,
                anomaly_type=AnomalyType.UNUSUAL_PATTERN,
                severity=severity,
                detected_at=detected_at,
                description=description,
                z_score=None,  # Isolation Forest doesn't use Z-score
                price=float(bar['close']) if 'close' in bar.index else None,
                volume=float(bar['volume']) if 'volume' in bar.index else None,
                raw_data={
                    "detector": "isolation_forest",
                    "anomaly_score": float(anomaly_score),
                    "prediction": int(prediction),
                    "features": {k: float(v) for k, v in feature_values.items()},
                    "contamination": self.contamination,
                    "n_estimators": self.n_estimators,
                    "bar_data": {
                        "open": float(bar['open']) if 'open' in bar.index else None,
                        "high": float(bar['high']) if 'high' in bar.index else None,
                        "low": float(bar['low']) if 'low' in bar.index else None,
                        "close": float(bar['close']) if 'close' in bar.index else None,
                        "volume": float(bar['volume']) if 'volume' in bar.index else None,
                    }
                }
            )
            
            return anomaly
        
        # No anomaly detected
        return None
    
    def detect_batch(self, data: pd.DataFrame, instrument: str = "UNKNOWN",
                    asset_class: str = "equity", exchange: Optional[str] = None,
                    train_first: bool = True) -> List[AnomalyEvent]:
        """
        Detect anomalies in a batch of historical data.
        
        Args:
            data: DataFrame with OHLCV data
                  Required columns: open, high, low, close, volume
            instrument: Instrument symbol
            asset_class: Asset class
            exchange: Exchange name
            train_first: Whether to train model on the data first (default: True)
        
        Returns:
            List of AnomalyEvent objects for detected anomalies
        """
        # Train model if requested
        if train_first:
            model = self.train(data, instrument)
        else:
            model = self._load_model(instrument)
            if model is None:
                raise ValueError(
                    f"No trained model found for {instrument}. Set train_first=True or train manually."
                )
        
        # Compute features
        features = self._compute_features(data)
        
        if len(features) == 0:
            return []
        
        # Predict anomalies
        predictions = model.predict(features.values)
        anomaly_scores = model.score_samples(features.values)
        
        # Create anomaly events for detected anomalies
        anomalies = []
        
        # Get original indices (features may have fewer rows due to dropna)
        feature_indices = features.index
        
        for i, (pred, score) in enumerate(zip(predictions, anomaly_scores)):
            if pred == -1:
                # Anomaly detected
                original_idx = feature_indices[i]
                
                # Determine severity
                if score < -0.5:
                    severity = AnomalySeverity.CRITICAL
                elif score < -0.3:
                    severity = AnomalySeverity.HIGH
                else:
                    severity = AnomalySeverity.MEDIUM
                
                # Get bar data
                bar = data.iloc[original_idx]
                
                # Parse timestamp
                try:
                    if 'timestamp' in data.columns:
                        detected_at = pd.to_datetime(data.iloc[original_idx]['timestamp'])
                        if detected_at.tzinfo is None:
                            detected_at = detected_at.tz_localize('UTC')
                    else:
                        detected_at = datetime.utcnow()
                except (ValueError, AttributeError, KeyError):
                    detected_at = datetime.utcnow()
                
                # Build description
                feature_values = features.iloc[i].to_dict()
                description = (
                    f"Isolation Forest anomaly detected: unusual multi-dimensional pattern. "
                    f"Anomaly score: {score:.3f}. "
                    f"Features: price_change={feature_values.get('price_change_pct', 0):.2f}%, "
                    f"volume_ratio={feature_values.get('volume_ratio', 0):.2f}x, "
                    f"atr_change={feature_values.get('atr_change_pct', 0):.2f}%, "
                    f"high_low_range={feature_values.get('high_low_range', 0):.2f}%, "
                    f"close_position={feature_values.get('close_position_in_range', 0):.2f}"
                )
                
                # Create anomaly event
                anomaly = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument=instrument,
                    asset_class=asset_class,
                    exchange=exchange,
                    anomaly_type=AnomalyType.UNUSUAL_PATTERN,
                    severity=severity,
                    detected_at=detected_at,
                    description=description,
                    z_score=None,
                    price=float(bar['close']) if 'close' in bar.keys() else None,
                    volume=float(bar['volume']) if 'volume' in bar.keys() else None,
                    raw_data={
                        "detector": "isolation_forest",
                        "anomaly_score": float(score),
                        "prediction": int(pred),
                        "features": {k: float(v) for k, v in feature_values.items()},
                        "contamination": self.contamination,
                        "n_estimators": self.n_estimators,
                        "bar_index": int(original_idx),
                    }
                )
                
                anomalies.append(anomaly)
        
        return anomalies
