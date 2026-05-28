"""
CUSUM (Cumulative Sum Control Chart) Anomaly Detector

Implements CUSUM algorithm for detecting structural breaks and regime changes.
Requirements: 11.3

Algorithm:
- CUSUM tracks cumulative deviations from the mean
- Better than Z-score for detecting gradual regime shifts and sustained deviations
- Uses two cumulative sums: positive (upward shifts) and negative (downward shifts)
- Parameters: h=5.0 (decision threshold), k=0.5 (allowance/reference value)

Detects:
- Regime changes: sustained shifts in price level or volatility
- Structural breaks: changes in market behavior patterns
- Trend breaks: transitions between trending and ranging markets

CUSUM Formula:
- S_pos(t) = max(0, S_pos(t-1) + z(t) - k)
- S_neg(t) = max(0, S_neg(t-1) - z(t) - k)
- Alert when S_pos > h (upward shift) or S_neg > h (downward shift)
- Reset cumulative sum to 0 after alarm

Where:
- z(t) = (value - mean) / std (standardized value)
- k = allowance (typically 0.5) - filters out small random variations
- h = decision threshold (typically 5.0) - triggers alarm
"""

import numpy as np
from typing import List, Optional
from datetime import datetime
import uuid

from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


class CUSUMDetector:
    """
    CUSUM (Cumulative Sum Control Chart) detector for structural breaks.
    
    Better than Z-score for detecting gradual regime shifts and sustained
    deviations from the mean (not just single spikes).
    
    Used for detecting:
    - Market regime changes (bull to bear, trending to ranging)
    - Structural breaks in price patterns
    - Volatility regime shifts
    """
    
    def __init__(self, h: float = 5.0, k: float = 0.5):
        """
        Initialize the CUSUM detector.
        
        Args:
            h: Decision threshold (alarm limit). Default: 5.0 (industry standard)
            k: Allowance (reference value). Default: 0.5 (industry standard)
               Filters out small random variations
        """
        self.h = h  # Decision threshold
        self.k = k  # Allowance
        self.cusum_pos = 0.0  # Cumulative sum for upward shifts
        self.cusum_neg = 0.0  # Cumulative sum for downward shifts
    
    def reset(self):
        """Reset the cumulative sums to zero."""
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
    
    def update(self, value: float, mean: float, std: float) -> Optional[str]:
        """
        Update CUSUM with a new value and check for regime shift.
        
        This method is designed for online/streaming detection where values
        arrive one at a time.
        
        Args:
            value: Current value to process
            mean: Reference mean (typically rolling window mean)
            std: Reference standard deviation (typically rolling window std)
        
        Returns:
            "upward_shift" if upward regime change detected
            "downward_shift" if downward regime change detected
            None if no shift detected
        """
        # Handle zero standard deviation
        if std == 0:
            return None
        
        # Standardize the value
        z = (value - mean) / std
        
        # Update cumulative sums
        self.cusum_pos = max(0, self.cusum_pos + z - self.k)
        self.cusum_neg = max(0, self.cusum_neg - z - self.k)
        
        # Check for alarms
        if self.cusum_pos > self.h:
            self.cusum_pos = 0  # Reset after alarm
            return "upward_shift"
        
        if self.cusum_neg > self.h:
            self.cusum_neg = 0  # Reset after alarm
            return "downward_shift"
        
        return None
    
    def detect_batch(self, series: np.ndarray, timestamps: List[str],
                    instrument: str = "UNKNOWN", asset_class: str = "equity",
                    exchange: Optional[str] = None,
                    window_size: int = 20) -> List[AnomalyEvent]:
        """
        Detect regime changes in a batch time series.
        
        This method processes an entire series at once, using a rolling window
        to compute mean and std for each point.
        
        Args:
            series: NumPy array of values (e.g., prices or returns)
            timestamps: List of ISO timestamp strings corresponding to each value
            instrument: Instrument symbol (default: "UNKNOWN")
            asset_class: Asset class (default: "equity")
            exchange: Exchange name (optional)
            window_size: Size of rolling window for computing mean/std (default: 20)
        
        Returns:
            List of AnomalyEvent objects for detected regime changes
        """
        if len(series) < window_size:
            # Not enough data for rolling window analysis
            return []
        
        if len(series) != len(timestamps):
            raise ValueError(
                f"Series length ({len(series)}) must match timestamps length ({len(timestamps)})"
            )
        
        anomalies = []
        
        # Reset state at the beginning
        self.reset()
        
        # Process each point in the series
        for i in range(window_size, len(series)):
            # Get the window of data up to (but not including) current point
            window = series[i - window_size:i]
            current_value = series[i]
            
            # Calculate statistics
            mean = np.mean(window)
            std = np.std(window, ddof=1)  # Sample standard deviation
            
            # Update CUSUM and check for shift
            shift_direction = self.update(current_value, mean, std)
            
            if shift_direction is not None:
                # Regime change detected
                severity = AnomalySeverity.HIGH  # Regime changes are always significant
                
                # Determine description based on direction
                if shift_direction == "upward_shift":
                    description = (
                        f"Upward regime shift detected: sustained upward deviation from mean. "
                        f"CUSUM positive threshold ({self.h}) exceeded at value {current_value:.2f} "
                        f"(window mean: {mean:.2f}, std: {std:.2f})"
                    )
                else:  # downward_shift
                    description = (
                        f"Downward regime shift detected: sustained downward deviation from mean. "
                        f"CUSUM negative threshold ({self.h}) exceeded at value {current_value:.2f} "
                        f"(window mean: {mean:.2f}, std: {std:.2f})"
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
                    anomaly_type=AnomalyType.REGIME_CHANGE,
                    severity=severity,
                    detected_at=detected_at,
                    description=description,
                    z_score=None,  # CUSUM doesn't use Z-score directly
                    price=float(current_value),
                    volume=None,
                    raw_data={
                        "detector": "cusum",
                        "shift_direction": shift_direction,
                        "current_value": float(current_value),
                        "window_mean": float(mean),
                        "window_std": float(std),
                        "cusum_h": self.h,
                        "cusum_k": self.k,
                        "window_size": window_size,
                        "bar_index": i,
                        "timestamp": timestamps[i]
                    }
                )
                
                anomalies.append(anomaly)
        
        return anomalies
