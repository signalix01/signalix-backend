"""
Unit tests for ZScoreDetector

Tests Requirements: 11.2
- Rolling window of 20 periods
- Alert when |Z| ≥ 3.0 (high severity)
- Critical when |Z| ≥ 4.0 (critical severity)
- Detect price spikes and volume surges
- Verify detection at correct bar index
- Verify severity levels
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import List

from services.alerts.detectors.zscore import ZScoreDetector
from shared.database.models import AnomalyType, AnomalySeverity


def generate_timestamps(start: datetime, count: int, interval_minutes: int = 1) -> List[str]:
    """Generate a list of ISO timestamp strings."""
    return [
        (start + timedelta(minutes=i)).isoformat()
        for i in range(count)
    ]


class TestZScoreDetectorBasic:
    """Basic functionality tests for ZScoreDetector."""
    
    def test_initialization_default_params(self):
        """Test detector initialization with default parameters."""
        detector = ZScoreDetector()
        assert detector.window_size == 20
        assert detector.alert_threshold == 3.0
        assert detector.critical_threshold == 4.0
    
    def test_initialization_custom_params(self):
        """Test detector initialization with custom parameters."""
        detector = ZScoreDetector(window_size=30, alert_threshold=2.5, critical_threshold=3.5)
        assert detector.window_size == 30
        assert detector.alert_threshold == 2.5
        assert detector.critical_threshold == 3.5
    
    def test_insufficient_data(self):
        """Test that detector returns empty list when data is insufficient."""
        detector = ZScoreDetector(window_size=20)
        
        # Only 15 data points (less than window_size)
        series = np.array([100.0] * 15)
        timestamps = generate_timestamps(datetime.utcnow(), 15)
        
        anomalies = detector.detect(series, timestamps, "price", "TEST")
        assert len(anomalies) == 0
    
    def test_mismatched_lengths(self):
        """Test that detector raises error when series and timestamps lengths don't match."""
        detector = ZScoreDetector()
        
        series = np.array([100.0] * 25)
        timestamps = generate_timestamps(datetime.utcnow(), 20)  # Different length
        
        with pytest.raises(ValueError, match="Series length.*must match timestamps length"):
            detector.detect(series, timestamps, "price", "TEST")


class TestZScoreDetectorPriceSpike:
    """Tests for price spike detection."""
    
    def test_no_spike_stable_prices(self):
        """Test that no anomalies are detected in stable price data."""
        detector = ZScoreDetector()
        
        # Stable prices around 100 with small random noise
        np.random.seed(42)
        series = np.random.normal(100, 0.5, 30)
        timestamps = generate_timestamps(datetime.utcnow(), 30)
        
        anomalies = detector.detect(series, timestamps, "price", "STABLE")
        assert len(anomalies) == 0
    
    def test_high_severity_price_spike(self):
        """Test detection of high severity price spike (|Z| ≥ 3.0)."""
        detector = ZScoreDetector(window_size=20)
        
        # Create synthetic data: prices with small variation then a spike
        # Use small random noise to avoid zero std
        np.random.seed(42)
        base_price = 100.0
        series = np.random.normal(base_price, 0.1, 20)  # Small noise
        series = np.append(series, base_price + 0.35)  # Moderate spike (adjusted to get Z between 3-4)
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "SPIKE_TEST", "equity", "NSE")
        
        # Should detect exactly one anomaly
        assert len(anomalies) == 1
        
        anomaly = anomalies[0]
        assert anomaly.anomaly_type == AnomalyType.PRICE_SPIKE
        assert anomaly.severity == AnomalySeverity.HIGH
        assert anomaly.instrument == "SPIKE_TEST"
        assert anomaly.asset_class == "equity"
        assert anomaly.exchange == "NSE"
        assert abs(anomaly.z_score) >= 3.0
        assert abs(anomaly.z_score) < 4.0
        assert "price spike" in anomaly.description.lower()
        
        # Verify raw_data contains correct information
        assert anomaly.raw_data["bar_index"] == 20
        assert anomaly.raw_data["metric_name"] == "price"
        assert anomaly.raw_data["window_size"] == 20
    
    def test_critical_severity_price_spike(self):
        """Test detection of critical severity price spike (|Z| ≥ 4.0)."""
        detector = ZScoreDetector(window_size=20)
        
        # Create synthetic data with a very large spike
        base_price = 100.0
        series = np.array([base_price] * 20 + [base_price + 20.0])  # Large spike
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "CRITICAL_SPIKE")
        
        assert len(anomalies) == 1
        anomaly = anomalies[0]
        assert anomaly.severity == AnomalySeverity.CRITICAL
        assert abs(anomaly.z_score) >= 4.0
    
    def test_downward_price_spike(self):
        """Test detection of downward price spike (negative Z-score)."""
        detector = ZScoreDetector(window_size=20)
        
        # Create synthetic data with a downward spike
        base_price = 100.0
        series = np.array([base_price] * 20 + [base_price - 15.0])  # Downward spike
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "DOWN_SPIKE")
        
        assert len(anomalies) == 1
        anomaly = anomalies[0]
        assert anomaly.z_score < 0  # Negative Z-score
        assert "downward" in anomaly.description.lower()
    
    def test_multiple_price_spikes(self):
        """Test detection of multiple price spikes in a series."""
        detector = ZScoreDetector(window_size=20)
        
        # Create data with two spikes at different positions
        base_price = 100.0
        series = np.array(
            [base_price] * 20 +  # Window
            [base_price + 15.0] +  # First spike at index 20
            [base_price] * 10 +  # Normal prices
            [base_price + 16.0]  # Second spike at index 31
        )
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect(series, timestamps, "price", "MULTI_SPIKE")
        
        # Should detect both spikes
        assert len(anomalies) == 2
        assert anomalies[0].raw_data["bar_index"] == 20
        assert anomalies[1].raw_data["bar_index"] == 31
    
    def test_price_spike_convenience_method(self):
        """Test the detect_price_spike convenience method."""
        detector = ZScoreDetector(window_size=20)
        
        base_price = 100.0
        prices = np.array([base_price] * 20 + [base_price + 15.0])
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect_price_spike(
            prices, timestamps, "CONV_TEST", "equity", "NSE"
        )
        
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.PRICE_SPIKE


class TestZScoreDetectorVolumeSurge:
    """Tests for volume surge detection."""
    
    def test_no_surge_stable_volume(self):
        """Test that no anomalies are detected in stable volume data."""
        detector = ZScoreDetector()
        
        # Stable volume with small variations
        np.random.seed(42)
        series = np.random.normal(10000, 500, 30)
        timestamps = generate_timestamps(datetime.utcnow(), 30)
        
        anomalies = detector.detect(series, timestamps, "volume", "STABLE_VOL")
        assert len(anomalies) == 0
    
    def test_high_severity_volume_surge(self):
        """Test detection of high severity volume surge (|Z| ≥ 3.0)."""
        detector = ZScoreDetector(window_size=20)
        
        # Create synthetic data: stable volume with some variation then a surge
        # Add small random noise to avoid zero std
        np.random.seed(42)
        base_volume = 10000.0
        series = np.random.normal(base_volume, 100, 20)  # Small noise
        series = np.append(series, base_volume + 350)  # Moderate surge (adjusted to get Z between 3-4)
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "volume", "VOL_SURGE", "equity", "NSE")
        
        assert len(anomalies) == 1
        
        anomaly = anomalies[0]
        assert anomaly.anomaly_type == AnomalyType.VOLUME_SURGE
        assert anomaly.severity == AnomalySeverity.HIGH
        assert anomaly.instrument == "VOL_SURGE"
        assert abs(anomaly.z_score) >= 3.0
        assert abs(anomaly.z_score) < 4.0
        assert "volume surge" in anomaly.description.lower()
    
    def test_critical_severity_volume_surge(self):
        """Test detection of critical severity volume surge (|Z| ≥ 4.0)."""
        detector = ZScoreDetector(window_size=20)
        
        # Create synthetic data with a very large volume surge
        base_volume = 10000.0
        series = np.array([base_volume] * 20 + [base_volume * 5.0])  # 5x surge
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "volume", "CRITICAL_VOL")
        
        assert len(anomalies) == 1
        anomaly = anomalies[0]
        assert anomaly.severity == AnomalySeverity.CRITICAL
        assert abs(anomaly.z_score) >= 4.0
    
    def test_volume_surge_convenience_method(self):
        """Test the detect_volume_surge convenience method."""
        detector = ZScoreDetector(window_size=20)
        
        base_volume = 10000.0
        volumes = np.array([base_volume] * 20 + [base_volume * 4.0])
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect_volume_surge(
            volumes, timestamps, "CONV_VOL", "equity", "BSE"
        )
        
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.VOLUME_SURGE


class TestZScoreDetectorEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_zero_standard_deviation(self):
        """Test handling of zero standard deviation (no variation in window)."""
        detector = ZScoreDetector(window_size=20)
        
        # All values in window are identical
        series = np.array([100.0] * 25)
        timestamps = generate_timestamps(datetime.utcnow(), 25)
        
        # Should not crash, should return empty list
        anomalies = detector.detect(series, timestamps, "price", "ZERO_STD")
        assert len(anomalies) == 0
    
    def test_exact_window_size(self):
        """Test with data length exactly equal to window size."""
        detector = ZScoreDetector(window_size=20)
        
        # Exactly 20 data points
        series = np.array([100.0] * 20)
        timestamps = generate_timestamps(datetime.utcnow(), 20)
        
        # Should return empty list (need at least window_size + 1)
        anomalies = detector.detect(series, timestamps, "price", "EXACT_SIZE")
        assert len(anomalies) == 0
    
    def test_window_size_plus_one(self):
        """Test with data length equal to window size + 1."""
        detector = ZScoreDetector(window_size=20)
        
        # 21 data points with spike at the end
        base_price = 100.0
        series = np.array([base_price] * 20 + [base_price + 15.0])
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "SIZE_PLUS_ONE")
        
        # Should detect the spike at index 20
        assert len(anomalies) == 1
        assert anomalies[0].raw_data["bar_index"] == 20
    
    def test_spike_at_exact_threshold(self):
        """Test spike exactly at the alert threshold."""
        detector = ZScoreDetector(window_size=20, alert_threshold=3.0)
        
        # Create data where Z-score is exactly 3.0
        # For a constant series with std=1, a value 3 std away gives Z=3.0
        mean = 100.0
        std = 5.0
        series = np.random.normal(mean, std, 20)
        spike_value = mean + (3.0 * std)  # Exactly 3.0 standard deviations
        series = np.append(series, spike_value)
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "THRESHOLD_TEST")
        
        # Should detect (threshold is inclusive: |Z| ≥ 3.0)
        assert len(anomalies) >= 1
    
    def test_custom_metric_name(self):
        """Test detection with a custom metric name (not price or volume)."""
        detector = ZScoreDetector(window_size=20)
        
        # Custom metric with spike
        series = np.array([50.0] * 20 + [80.0])
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "custom_metric", "CUSTOM")
        
        assert len(anomalies) == 1
        anomaly = anomalies[0]
        assert anomaly.anomaly_type == AnomalyType.UNUSUAL_PATTERN
        assert "custom_metric" in anomaly.description.lower()
    
    def test_timestamp_parsing(self):
        """Test that timestamps are correctly parsed."""
        detector = ZScoreDetector(window_size=20)
        
        base_time = datetime(2024, 1, 15, 10, 30, 0)
        series = np.array([100.0] * 20 + [115.0])
        timestamps = generate_timestamps(base_time, 21)
        
        anomalies = detector.detect(series, timestamps, "price", "TIME_TEST")
        
        assert len(anomalies) == 1
        # The detected_at should be close to the timestamp at index 20
        expected_time = base_time + timedelta(minutes=20)
        assert anomalies[0].detected_at.replace(tzinfo=None) == expected_time


class TestZScoreDetectorRealWorldScenarios:
    """Tests simulating real-world market scenarios."""
    
    def test_gradual_trend_no_spike(self):
        """Test that gradual trends don't trigger false positives."""
        detector = ZScoreDetector(window_size=20)
        
        # Gradual upward trend
        series = np.linspace(100, 110, 30)
        timestamps = generate_timestamps(datetime.utcnow(), 30)
        
        anomalies = detector.detect(series, timestamps, "price", "TREND")
        
        # Should not detect anomalies in gradual trend
        assert len(anomalies) == 0
    
    def test_volatile_but_normal_market(self):
        """Test that normal volatility doesn't trigger false positives."""
        detector = ZScoreDetector(window_size=20)
        
        # Volatile but within normal range (2 std)
        np.random.seed(42)
        series = np.random.normal(100, 2, 30)
        timestamps = generate_timestamps(datetime.utcnow(), 30)
        
        anomalies = detector.detect(series, timestamps, "price", "VOLATILE")
        
        # Should not detect anomalies
        assert len(anomalies) == 0
    
    def test_flash_crash_scenario(self):
        """Test detection of flash crash scenario (sudden large drop)."""
        detector = ZScoreDetector(window_size=20)
        
        # Simulate flash crash: stable then sudden drop
        base_price = 1000.0
        series = np.array([base_price] * 20 + [base_price * 0.85])  # 15% drop
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "price", "FLASH_CRASH")
        
        assert len(anomalies) == 1
        assert anomalies[0].z_score < 0  # Negative for downward movement
        assert anomalies[0].severity in [AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]
    
    def test_earnings_volume_spike(self):
        """Test detection of earnings announcement volume spike."""
        detector = ZScoreDetector(window_size=20)
        
        # Normal volume then earnings spike
        normal_volume = 100000.0
        series = np.array([normal_volume] * 20 + [normal_volume * 10.0])  # 10x volume
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect(series, timestamps, "volume", "EARNINGS")
        
        assert len(anomalies) == 1
        assert anomalies[0].severity == AnomalySeverity.CRITICAL
        assert anomalies[0].volume == normal_volume * 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
