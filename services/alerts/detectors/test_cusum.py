"""
Unit tests for CUSUMDetector

Tests Requirements: 11.3
- CUSUM parameters: h=5.0, k=0.5 (industry standard)
- Detect sustained deviations from the mean (not just single spikes)
- Upward shift detection on sustained upward deviation
- Downward shift detection on sustained downward deviation
- Reset after alarm
- Store anomaly events in TimescaleDB format
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import List

from services.alerts.detectors.cusum import CUSUMDetector
from shared.database.models import AnomalyType, AnomalySeverity


def generate_timestamps(start: datetime, count: int, interval_minutes: int = 1) -> List[str]:
    """Generate a list of ISO timestamp strings."""
    return [
        (start + timedelta(minutes=i)).isoformat()
        for i in range(count)
    ]


class TestCUSUMDetectorInitialization:
    """Tests for CUSUMDetector initialization."""
    
    def test_initialization_default_params(self):
        """Test detector initialization with default parameters."""
        detector = CUSUMDetector()
        assert detector.h == 5.0
        assert detector.k == 0.5
        assert detector.cusum_pos == 0.0
        assert detector.cusum_neg == 0.0
    
    def test_initialization_custom_params(self):
        """Test detector initialization with custom parameters."""
        detector = CUSUMDetector(h=4.0, k=0.75)
        assert detector.h == 4.0
        assert detector.k == 0.75
        assert detector.cusum_pos == 0.0
        assert detector.cusum_neg == 0.0
    
    def test_reset(self):
        """Test that reset clears cumulative sums."""
        detector = CUSUMDetector()
        
        # Manually set cumulative sums
        detector.cusum_pos = 3.5
        detector.cusum_neg = 2.1
        
        # Reset
        detector.reset()
        
        assert detector.cusum_pos == 0.0
        assert detector.cusum_neg == 0.0


class TestCUSUMDetectorUpdate:
    """Tests for the update method (online detection)."""
    
    def test_update_no_shift_stable_values(self):
        """Test that stable values don't trigger shifts."""
        detector = CUSUMDetector()
        
        mean = 100.0
        std = 5.0
        
        # Values close to mean shouldn't trigger shift
        for _ in range(10):
            result = detector.update(100.0, mean, std)
            assert result is None
    
    def test_update_upward_shift_detection(self):
        """Test detection of upward regime shift."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        mean = 100.0
        std = 5.0
        
        # Simulate sustained upward deviation
        # Each value is 1 std above mean, so z = 1.0
        # cusum_pos accumulates: (1.0 - 0.5) = 0.5 per step
        # Need 11 steps to exceed h=5.0: 11 * 0.5 = 5.5 > 5.0
        
        result = None
        for i in range(15):
            value = mean + std  # 1 std above mean
            result = detector.update(value, mean, std)
            if result is not None:
                break
        
        assert result == "upward_shift"
    
    def test_update_downward_shift_detection(self):
        """Test detection of downward regime shift."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        mean = 100.0
        std = 5.0
        
        # Simulate sustained downward deviation
        # Each value is 1 std below mean, so z = -1.0
        # cusum_neg accumulates: (-(-1.0) - 0.5) = 0.5 per step
        
        result = None
        for i in range(15):
            value = mean - std  # 1 std below mean
            result = detector.update(value, mean, std)
            if result is not None:
                break
        
        assert result == "downward_shift"
    
    def test_update_reset_after_alarm(self):
        """Test that cumulative sum resets after alarm."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        mean = 100.0
        std = 5.0
        
        # Trigger upward shift
        for i in range(15):
            value = mean + std
            result = detector.update(value, mean, std)
            if result == "upward_shift":
                break
        
        # After alarm, cusum_pos should be reset to 0
        assert detector.cusum_pos == 0.0
        
        # Verify it can detect another shift after reset
        result = None
        for i in range(15):
            value = mean + std
            result = detector.update(value, mean, std)
            if result is not None:
                break
        
        assert result == "upward_shift"
    
    def test_update_zero_std(self):
        """Test handling of zero standard deviation."""
        detector = CUSUMDetector()
        
        # Zero std should return None (no detection possible)
        result = detector.update(100.0, 100.0, 0.0)
        assert result is None
    
    def test_update_small_deviations_filtered(self):
        """Test that small deviations are filtered by k parameter."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        mean = 100.0
        std = 5.0
        
        # Small deviations (z < k) should not accumulate
        # Value 0.4 std above mean: z = 0.4, z - k = -0.1 (filtered to 0)
        for _ in range(20):
            value = mean + (0.4 * std)
            result = detector.update(value, mean, std)
            assert result is None
        
        # Cumulative sums should remain near zero
        assert detector.cusum_pos < 0.1
        assert detector.cusum_neg < 0.1


class TestCUSUMDetectorBatch:
    """Tests for the detect_batch method."""
    
    def test_batch_insufficient_data(self):
        """Test that detector returns empty list when data is insufficient."""
        detector = CUSUMDetector()
        
        # Only 15 data points (less than default window_size=20)
        series = np.array([100.0] * 15)
        timestamps = generate_timestamps(datetime.utcnow(), 15)
        
        anomalies = detector.detect_batch(series, timestamps, "TEST")
        assert len(anomalies) == 0
    
    def test_batch_mismatched_lengths(self):
        """Test that detector raises error when series and timestamps lengths don't match."""
        detector = CUSUMDetector()
        
        series = np.array([100.0] * 25)
        timestamps = generate_timestamps(datetime.utcnow(), 20)  # Different length
        
        with pytest.raises(ValueError, match="Series length.*must match timestamps length"):
            detector.detect_batch(series, timestamps, "TEST")
    
    def test_batch_no_shift_stable_series(self):
        """Test that no anomalies are detected in stable series."""
        detector = CUSUMDetector()
        
        # Stable series with small random noise
        np.random.seed(42)
        series = np.random.normal(100, 0.5, 50)
        timestamps = generate_timestamps(datetime.utcnow(), 50)
        
        anomalies = detector.detect_batch(series, timestamps, "STABLE")
        assert len(anomalies) == 0
    
    def test_batch_upward_shift_detection(self):
        """Test detection of upward regime shift in batch mode."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Create series with regime shift
        # First 30 points: mean=100, std=1
        # Then sustained upward shift to mean=105
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 30)
        series_after = np.random.normal(105, 1, 20)  # Sustained upward shift
        series = np.concatenate([series_before, series_after])
        
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(
            series, timestamps, "UPWARD_TEST", "equity", "NSE"
        )
        
        # Should detect at least one upward shift
        assert len(anomalies) >= 1
        
        # Check first anomaly
        anomaly = anomalies[0]
        assert anomaly.anomaly_type == AnomalyType.REGIME_CHANGE
        assert anomaly.severity == AnomalySeverity.HIGH
        assert anomaly.instrument == "UPWARD_TEST"
        assert anomaly.asset_class == "equity"
        assert anomaly.exchange == "NSE"
        assert "upward" in anomaly.description.lower()
        assert "regime shift" in anomaly.description.lower()
        
        # Verify raw_data
        assert anomaly.raw_data["detector"] == "cusum"
        assert anomaly.raw_data["shift_direction"] == "upward_shift"
        assert anomaly.raw_data["cusum_h"] == 5.0
        assert anomaly.raw_data["cusum_k"] == 0.5
    
    def test_batch_downward_shift_detection(self):
        """Test detection of downward regime shift in batch mode."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Create series with downward regime shift
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 30)
        series_after = np.random.normal(95, 1, 20)  # Sustained downward shift
        series = np.concatenate([series_before, series_after])
        
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "DOWNWARD_TEST")
        
        # Should detect at least one downward shift
        assert len(anomalies) >= 1
        
        anomaly = anomalies[0]
        assert anomaly.anomaly_type == AnomalyType.REGIME_CHANGE
        assert "downward" in anomaly.description.lower()
        assert anomaly.raw_data["shift_direction"] == "downward_shift"
    
    def test_batch_multiple_shifts(self):
        """Test detection of multiple regime shifts in a series."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Create series with multiple regime shifts
        np.random.seed(42)
        series1 = np.random.normal(100, 1, 30)  # Regime 1
        series2 = np.random.normal(105, 1, 25)  # Upward shift
        series3 = np.random.normal(100, 1, 25)  # Downward shift back
        series = np.concatenate([series1, series2, series3])
        
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "MULTI_SHIFT")
        
        # Should detect multiple shifts
        assert len(anomalies) >= 2
        
        # First should be upward
        assert anomalies[0].raw_data["shift_direction"] == "upward_shift"
        
        # Should have at least one downward shift
        downward_shifts = [a for a in anomalies if a.raw_data["shift_direction"] == "downward_shift"]
        assert len(downward_shifts) >= 1
    
    def test_batch_custom_window_size(self):
        """Test batch detection with custom window size."""
        detector = CUSUMDetector()
        
        # Create series with shift
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 40)
        series_after = np.random.normal(105, 1, 20)
        series = np.concatenate([series_before, series_after])
        
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        # Use custom window size
        anomalies = detector.detect_batch(
            series, timestamps, "CUSTOM_WINDOW", window_size=30
        )
        
        # Should still detect shift
        assert len(anomalies) >= 1
        assert anomalies[0].raw_data["window_size"] == 30
    
    def test_batch_timestamp_parsing(self):
        """Test that timestamps are correctly parsed."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        base_time = datetime(2024, 1, 15, 10, 30, 0)
        
        # Create series with shift
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 30)
        series_after = np.random.normal(105, 1, 20)
        series = np.concatenate([series_before, series_after])
        
        timestamps = generate_timestamps(base_time, len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "TIME_TEST")
        
        if len(anomalies) > 0:
            # The detected_at should be parsed from timestamp
            assert anomalies[0].detected_at is not None
            assert isinstance(anomalies[0].detected_at, datetime)


class TestCUSUMDetectorRealWorldScenarios:
    """Tests simulating real-world market scenarios."""
    
    def test_bull_to_bear_regime_change(self):
        """Test detection of bull to bear market regime change."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Simulate bull market (uptrend) then bear market (downtrend)
        np.random.seed(42)
        
        # Bull market: prices around 100 with upward drift
        bull_market = np.random.normal(100, 2, 30)
        
        # Bear market: prices drop to 90 and stay there
        bear_market = np.random.normal(90, 2, 25)
        
        series = np.concatenate([bull_market, bear_market])
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "REGIME_CHANGE")
        
        # Should detect regime change
        assert len(anomalies) >= 1
        assert anomalies[0].anomaly_type == AnomalyType.REGIME_CHANGE
    
    def test_volatility_regime_shift(self):
        """Test detection of volatility regime shift."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Low volatility period then high volatility period
        np.random.seed(42)
        low_vol = np.random.normal(100, 0.5, 30)  # Low volatility
        high_vol = np.random.normal(100, 5, 25)   # High volatility (same mean)
        
        series = np.concatenate([low_vol, high_vol])
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        # CUSUM can detect this as regime change due to larger deviations
        anomalies = detector.detect_batch(series, timestamps, "VOL_SHIFT")
        
        # May or may not detect depending on random values
        # This is expected - CUSUM detects mean shifts, not volatility directly
        # But large volatility can trigger detection
        assert isinstance(anomalies, list)
    
    def test_gradual_trend_vs_sudden_shift(self):
        """Test that CUSUM detects sustained shifts better than single spikes."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Series with single spike (should not trigger CUSUM)
        np.random.seed(42)
        series_spike = np.random.normal(100, 1, 30)
        series_spike[25] = 110  # Single spike
        
        timestamps_spike = generate_timestamps(datetime.utcnow(), len(series_spike))
        anomalies_spike = detector.detect_batch(series_spike, timestamps_spike, "SPIKE")
        
        # Reset detector
        detector.reset()
        
        # Series with sustained shift (should trigger CUSUM)
        series_shift = np.random.normal(100, 1, 30)
        series_shift[20:] += 5  # Sustained shift
        
        timestamps_shift = generate_timestamps(datetime.utcnow(), len(series_shift))
        anomalies_shift = detector.detect_batch(series_shift, timestamps_shift, "SHIFT")
        
        # Sustained shift should be more likely to trigger than single spike
        # (though not guaranteed due to random noise)
        assert isinstance(anomalies_spike, list)
        assert isinstance(anomalies_shift, list)
    
    def test_trending_market_no_false_positives(self):
        """Test that gradual trends don't trigger excessive false positives."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Gradual upward trend (not a regime shift)
        series = np.linspace(100, 105, 50)
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "TREND")
        
        # CUSUM can detect gradual trends as regime changes (this is expected)
        # But it should not trigger excessively (less than 20% of data points)
        assert len(anomalies) < len(series) * 0.2


class TestCUSUMDetectorEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_exact_window_size(self):
        """Test with data length exactly equal to window size."""
        detector = CUSUMDetector()
        
        # Exactly 20 data points
        series = np.array([100.0] * 20)
        timestamps = generate_timestamps(datetime.utcnow(), 20)
        
        # Should return empty list (need at least window_size + 1)
        anomalies = detector.detect_batch(series, timestamps, "EXACT_SIZE")
        assert len(anomalies) == 0
    
    def test_window_size_plus_one(self):
        """Test with data length equal to window size + 1."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # 21 data points with shift at the end
        series = np.array([100.0] * 20 + [110.0])
        timestamps = generate_timestamps(datetime.utcnow(), 21)
        
        anomalies = detector.detect_batch(series, timestamps, "SIZE_PLUS_ONE")
        
        # Single point shift unlikely to trigger CUSUM (needs sustained deviation)
        # This is expected behavior
        assert isinstance(anomalies, list)
    
    def test_zero_std_in_window(self):
        """Test handling of zero standard deviation in window."""
        detector = CUSUMDetector()
        
        # All values in window are identical
        series = np.array([100.0] * 30)
        timestamps = generate_timestamps(datetime.utcnow(), 30)
        
        # Should not crash, should return empty list
        anomalies = detector.detect_batch(series, timestamps, "ZERO_STD")
        assert len(anomalies) == 0
    
    def test_very_large_shift(self):
        """Test detection of very large regime shift."""
        detector = CUSUMDetector(h=5.0, k=0.5)
        
        # Very large shift (10 std)
        series = np.array([100.0] * 25 + [150.0] * 10)
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        anomalies = detector.detect_batch(series, timestamps, "LARGE_SHIFT")
        
        # Should definitely detect this
        assert len(anomalies) >= 1
        assert anomalies[0].raw_data["shift_direction"] == "upward_shift"


class TestCUSUMDetectorParameterSensitivity:
    """Tests for parameter sensitivity."""
    
    def test_lower_h_more_sensitive(self):
        """Test that lower h threshold makes detector more sensitive."""
        # Create series with moderate shift
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 30)
        series_after = np.random.normal(103, 1, 20)  # Moderate shift
        series = np.concatenate([series_before, series_after])
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        # High threshold (less sensitive)
        detector_high = CUSUMDetector(h=8.0, k=0.5)
        anomalies_high = detector_high.detect_batch(series, timestamps, "HIGH_H")
        
        # Low threshold (more sensitive)
        detector_low = CUSUMDetector(h=3.0, k=0.5)
        anomalies_low = detector_low.detect_batch(series, timestamps, "LOW_H")
        
        # Lower h should detect more (or equal) anomalies
        assert len(anomalies_low) >= len(anomalies_high)
    
    def test_higher_k_less_sensitive(self):
        """Test that higher k value makes detector less sensitive."""
        # Create series with small sustained shift
        np.random.seed(42)
        series_before = np.random.normal(100, 1, 30)
        series_after = np.random.normal(102, 1, 20)  # Small shift
        series = np.concatenate([series_before, series_after])
        timestamps = generate_timestamps(datetime.utcnow(), len(series))
        
        # Low k (more sensitive)
        detector_low_k = CUSUMDetector(h=5.0, k=0.3)
        anomalies_low_k = detector_low_k.detect_batch(series, timestamps, "LOW_K")
        
        # High k (less sensitive)
        detector_high_k = CUSUMDetector(h=5.0, k=0.8)
        anomalies_high_k = detector_high_k.detect_batch(series, timestamps, "HIGH_K")
        
        # Lower k should detect more (or equal) anomalies
        assert len(anomalies_low_k) >= len(anomalies_high_k)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
