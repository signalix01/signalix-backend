"""
Z-Score Anomaly Detector

Implements statistical anomaly detection using Z-score (standard score) method.
Requirements: 11.2

Algorithm:
- Uses a rolling window of 20 periods to compute mean and standard deviation
- Calculates Z-score: Z = (X - μ) / σ
- Alert when |Z| ≥ 3.0 (high severity)
- Critical when |Z| ≥ 4.0 (critical severity)

Detects:
- Price spikes: sudden price movements beyond normal volatility
- Volume surges: abnormal trading volume compared to historical average
"""

import numpy as np
from typing import List, Optional
from datetime import datetime
import uuid

from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


class ZScoreDetector:
    """
    Z-Score based anomaly detector for time series data.
    
    Uses rolling window statistics to identify outliers that deviate
    significantly from the mean behavior.
    """
    
    def __init__(self, window_size: int = 20, alert_threshold: float = 3.0, 
                 critical_threshold: float = 4.0):
        """
        Initialize the Z-Score detector.
        
        Args:
            window_size: Number of periods for rolling window (default: 20)
            alert_threshold: Z-score threshold for high severity alerts (default: 3.0)
            critical_threshold: Z-score threshold for critical alerts (default: 4.0)
        """
        self.window_size = window_size
        self.alert_threshold = alert_threshold
        self.critical_threshold = critical_threshold
    
    def detect(self, series: np.ndarray, timestamps: List[str], 
               metric_name: str, instrument: str = "UNKNOWN",
               asset_class: str = "equity", exchange: Optional[str] = None) -> List[AnomalyEvent]:
        """
        Detect anomalies in a time series using Z-score method.
        
        Args:
            series: NumPy array of values (e.g., prices or volumes)
            timestamps: List of ISO timestamp strings corresponding to each value
            metric_name: Name of the metric being analyzed ("price" or "volume")
            instrument: Instrument symbol (default: "UNKNOWN")
            asset_class: Asset class (default: "equity")
            exchange: Exchange name (optional)
        
        Returns:
            List of AnomalyEvent objects for detected anomalies
        """
        if len(series) < self.window_size:
            # Not enough data for rolling window analysis
            return []
        
        if len(series) != len(timestamps):
            raise ValueError(f"Series length ({len(series)}) must match timestamps length ({len(timestamps)})")
        
        anomalies = []
        
        # Calculate rolling mean and std for each point
        for i in range(self.window_size, len(series)):
            # Get the window of data up to (but not including) current point
            window = series[i - self.window_size:i]
            current_value = series[i]
            
            # Calculate statistics
            mean = np.mean(window)
            std = np.std(window, ddof=1)  # Sample standard deviation
            
            # Handle zero standard deviation case
            if std == 0:
                # If std is 0 and current value differs from mean, it's a significant anomaly
                if abs(current_value - mean) > 1e-10:  # Use small epsilon for float comparison
                    # Treat as maximum anomaly (infinite Z-score)
                    # Use a large but finite value for practical purposes
                    z_score = 10.0 if current_value > mean else -10.0
                    abs_z_score = 10.0
                else:
                    # No variation at all, skip
                    continue
            else:
                # Calculate Z-score normally
                z_score = (current_value - mean) / std
                abs_z_score = abs(z_score)
            
            # Check if anomaly detected
            if abs_z_score >= self.alert_threshold:
                # Determine severity
                if abs_z_score >= self.critical_threshold:
                    severity = AnomalySeverity.CRITICAL
                else:
                    severity = AnomalySeverity.HIGH
                
                # Determine anomaly type based on metric and direction
                if metric_name.lower() == "price":
                    anomaly_type = AnomalyType.PRICE_SPIKE
                    direction = "upward" if z_score > 0 else "downward"
                    description = (
                        f"{direction.capitalize()} price spike detected: "
                        f"value {current_value:.2f} is {abs_z_score:.2f} standard deviations "
                        f"from the {self.window_size}-period mean ({mean:.2f})"
                    )
                elif metric_name.lower() == "volume":
                    anomaly_type = AnomalyType.VOLUME_SURGE
                    description = (
                        f"Volume surge detected: "
                        f"value {current_value:.0f} is {abs_z_score:.2f} standard deviations "
                        f"above the {self.window_size}-period mean ({mean:.0f})"
                    )
                else:
                    # Generic anomaly for other metrics
                    anomaly_type = AnomalyType.UNUSUAL_PATTERN
                    direction = "above" if z_score > 0 else "below"
                    description = (
                        f"Anomaly in {metric_name}: "
                        f"value {current_value:.2f} is {abs_z_score:.2f} standard deviations "
                        f"{direction} the {self.window_size}-period mean ({mean:.2f})"
                    )
                
                # Parse timestamp
                try:
                    detected_at = datetime.fromisoformat(timestamps[i].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    detected_at = datetime.utcnow()
                
                # Create anomaly event
                anomaly = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument=instrument,
                    asset_class=asset_class,
                    exchange=exchange,
                    anomaly_type=anomaly_type,
                    severity=severity,
                    detected_at=detected_at,
                    description=description,
                    z_score=float(z_score),
                    price=float(current_value) if metric_name.lower() == "price" else None,
                    volume=float(current_value) if metric_name.lower() == "volume" else None,
                    raw_data={
                        "metric_name": metric_name,
                        "current_value": float(current_value),
                        "window_mean": float(mean),
                        "window_std": float(std),
                        "z_score": float(z_score),
                        "abs_z_score": float(abs_z_score),
                        "window_size": self.window_size,
                        "bar_index": i,
                        "timestamp": timestamps[i]
                    }
                )
                
                anomalies.append(anomaly)
        
        return anomalies
    
    def detect_price_spike(self, prices: np.ndarray, timestamps: List[str],
                          instrument: str = "UNKNOWN", asset_class: str = "equity",
                          exchange: Optional[str] = None) -> List[AnomalyEvent]:
        """
        Convenience method to detect price spikes.
        
        Args:
            prices: NumPy array of price values
            timestamps: List of ISO timestamp strings
            instrument: Instrument symbol
            asset_class: Asset class
            exchange: Exchange name
        
        Returns:
            List of AnomalyEvent objects for detected price spikes
        """
        return self.detect(prices, timestamps, "price", instrument, asset_class, exchange)
    
    def detect_volume_surge(self, volumes: np.ndarray, timestamps: List[str],
                           instrument: str = "UNKNOWN", asset_class: str = "equity",
                           exchange: Optional[str] = None) -> List[AnomalyEvent]:
        """
        Convenience method to detect volume surges.
        
        Args:
            volumes: NumPy array of volume values
            timestamps: List of ISO timestamp strings
            instrument: Instrument symbol
            asset_class: Asset class
            exchange: Exchange name
        
        Returns:
            List of AnomalyEvent objects for detected volume surges
        """
        return self.detect(volumes, timestamps, "volume", instrument, asset_class, exchange)
