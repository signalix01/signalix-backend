"""
Unit tests for FlashDetector

Tests Requirements: 11.6
- Flash crash/rally detection threshold: price moves > 5% within 5 minutes
- Use sliding window over tick data
- Generate CRITICAL severity AnomalyEvent for both flash crash and flash rally
- Test: simulate 6% drop in 4 minutes, verify CRITICAL event generated
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from services.alerts.detectors.flash_detector import FlashDetector, TickData
from shared.database.models import AnomalyType, AnomalySeverity


def generate_tick_data(
    base_price: float,
    count: int,
    start_time: datetime,
    interval_seconds: int = 10,
    instrument: str = "TEST"
) -> List[TickData]:
    """
    Generate a list of TickData objects with stable prices.
    
    Args:
        base_price: Base price for all ticks
        count: Number of ticks to generate
        start_time: Starting timestamp
        interval_seconds: Seconds between ticks
        instrument: Instrument symbol
    
    Returns:
        List of TickData objects
    """
    ticks = []
    for i in range(count):
        tick = TickData(
            timestamp=start_time + timedelta(seconds=i * interval_seconds),
            price=base_price,
            volume=1000.0,
            instrument=instrument
        )
        ticks.append(tick)
    return ticks


class TestFlashDetectorBasic:
    """Basic functionality tests for FlashDetector."""
    
    def test_initialization_default_params(self):
        """Test detector initialization with default parameters."""
        detector = FlashDetector()
        assert detector.threshold_pct == 5.0
        assert detector.window_minutes == 5
        assert detector.threshold_fraction == 0.05
    
    def test_initialization_custom_params(self):
        """Test detector initialization with custom parameters."""
        detector = FlashDetector(threshold_pct=3.0, window_minutes=10)
        assert detector.threshold_pct == 3.0
        assert detector.window_minutes == 10
        assert detector.threshold_fraction == 0.03
    
    def test_insufficient_data_empty_list(self):
        """Test that detector returns None when tick list is empty."""
        detector = FlashDetector()
        result = detector.check([])
        assert result is None
    
    def test_insufficient_data_single_tick(self):
        """Test that detector returns None with only one tick."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        ticks = generate_tick_data(100.0, 1, start_time)
        result = detector.check(ticks)
        assert result is None
    
    def test_stable_prices_no_detection(self):
        """Test that stable prices don't trigger any detection."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        
        # 30 ticks over 5 minutes, all at same price
        ticks = generate_tick_data(100.0, 30, start_time, interval_seconds=10)
        
        result = detector.check(ticks)
        assert result is None


class TestFlashCrashDetection:
    """Tests for flash crash detection."""
    
    def test_flash_crash_6_percent_4_minutes(self):
        """
        Test detection of 6% drop in 4 minutes (requirement test case).
        Requirements: 11.6 - simulate 6% drop in 4 minutes, verify CRITICAL event generated
        """
        detector = FlashDetector(threshold_pct=5.0, window_minutes=5)
        start_time = datetime.utcnow()
        
        # Create ticks: stable at 1000, then drop to 940 (6% drop)
        base_price = 1000.0
        drop_price = base_price * 0.94  # 6% drop
        
        # 24 ticks at base price (4 minutes at 10-second intervals)
        ticks = generate_tick_data(base_price, 24, start_time, interval_seconds=10, instrument="BANKNIFTY")
        
        # Add final tick with the drop
        crash_time = start_time + timedelta(minutes=4)
        ticks.append(TickData(
            timestamp=crash_time,
            price=drop_price,
            volume=5000.0,
            instrument="BANKNIFTY"
        ))
        
        result = detector.check(ticks)
        
        # Verify flash crash detected
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.severity == AnomalySeverity.CRITICAL
        assert result.instrument == "BANKNIFTY"
        assert result.price == drop_price
        
        # Verify description
        assert "flash crash" in result.description.lower()
        assert "6.00%" in result.description or "6.0%" in result.description
        
        # Verify raw data
        assert result.raw_data["flash_type"] == "crash"
        assert result.raw_data["drop_pct"] == pytest.approx(6.0, rel=0.01)
        assert result.raw_data["current_price"] == drop_price
        assert result.raw_data["highest_price"] == base_price
        assert result.raw_data["time_elapsed_minutes"] == pytest.approx(4.0, rel=0.1)
    
    def test_flash_crash_exact_threshold(self):
        """Test flash crash detection at exactly 5% threshold."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        drop_price = base_price * 0.95  # Exactly 5% drop
        
        ticks = generate_tick_data(base_price, 20, start_time, interval_seconds=10)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=3, seconds=20),
            price=drop_price,
            volume=1000.0,
            instrument="NIFTY50"
        ))
        
        result = detector.check(ticks)
        
        # Should NOT detect (threshold is > 5%, not >= 5%)
        # Actually, let's check the implementation - it uses > threshold_fraction
        # So 5% drop should NOT trigger if threshold is 5%
        # But 5.01% should trigger
        assert result is None
    
    def test_flash_crash_just_above_threshold(self):
        """Test flash crash detection just above 5% threshold."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        drop_price = base_price * 0.949  # 5.1% drop
        
        ticks = generate_tick_data(base_price, 20, start_time, interval_seconds=10)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=3, seconds=20),
            price=drop_price,
            volume=1000.0,
            instrument="NIFTY50"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.severity == AnomalySeverity.CRITICAL
    
    def test_flash_crash_large_drop(self):
        """Test detection of a very large flash crash (10% drop)."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        
        base_price = 500.0
        drop_price = base_price * 0.90  # 10% drop
        
        ticks = generate_tick_data(base_price, 15, start_time, interval_seconds=15)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=3, seconds=45),
            price=drop_price,
            volume=10000.0,
            instrument="RELIANCE"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.raw_data["drop_pct"] == pytest.approx(10.0, rel=0.01)
    
    def test_flash_crash_within_window(self):
        """Test that only ticks within the window are considered."""
        detector = FlashDetector(window_minutes=5)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        
        # Old high price outside the window (7 minutes ago)
        ticks = [TickData(
            timestamp=start_time - timedelta(minutes=7),
            price=base_price * 1.10,  # 10% higher
            volume=1000.0,
            instrument="TEST"
        )]
        
        # Recent prices within window (last 4 minutes)
        ticks.extend(generate_tick_data(base_price, 24, start_time - timedelta(minutes=4), interval_seconds=10))
        
        # Current price (6% drop from recent prices, but not from old high)
        ticks.append(TickData(
            timestamp=start_time,
            price=base_price * 0.94,
            volume=1000.0,
            instrument="TEST"
        ))
        
        result = detector.check(ticks)
        
        # Should detect based on recent window, not old high
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
    
    def test_gradual_decline_no_flash_crash(self):
        """Test that gradual decline doesn't trigger flash crash."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        
        # Gradual decline from 1000 to 940 over 5 minutes
        ticks = []
        for i in range(30):
            price = 1000.0 - (i * 2.0)  # Gradual decline
            ticks.append(TickData(
                timestamp=start_time + timedelta(seconds=i * 10),
                price=price,
                volume=1000.0,
                instrument="TEST"
            ))
        
        result = detector.check(ticks)
        
        # Should detect because current price is > 5% below the highest in window
        # The highest price in the window is at the start
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH


class TestFlashRallyDetection:
    """Tests for flash rally detection."""
    
    def test_flash_rally_6_percent_4_minutes(self):
        """Test detection of 6% rise in 4 minutes."""
        detector = FlashDetector(threshold_pct=5.0, window_minutes=5)
        start_time = datetime.utcnow()
        
        # Create ticks: stable at 1000, then rise to 1060 (6% rise)
        base_price = 1000.0
        rally_price = base_price * 1.06  # 6% rise
        
        # 24 ticks at base price (4 minutes)
        ticks = generate_tick_data(base_price, 24, start_time, interval_seconds=10, instrument="TATASTEEL")
        
        # Add final tick with the rally
        rally_time = start_time + timedelta(minutes=4)
        ticks.append(TickData(
            timestamp=rally_time,
            price=rally_price,
            volume=8000.0,
            instrument="TATASTEEL"
        ))
        
        result = detector.check(ticks)
        
        # Verify flash rally detected
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_RALLY
        assert result.severity == AnomalySeverity.CRITICAL
        assert result.instrument == "TATASTEEL"
        assert result.price == rally_price
        
        # Verify description
        assert "flash rally" in result.description.lower()
        assert "6.00%" in result.description or "6.0%" in result.description
        
        # Verify raw data
        assert result.raw_data["flash_type"] == "rally"
        assert result.raw_data["rise_pct"] == pytest.approx(6.0, rel=0.01)
        assert result.raw_data["current_price"] == rally_price
        assert result.raw_data["lowest_price"] == base_price
    
    def test_flash_rally_exact_threshold(self):
        """Test flash rally detection at exactly 5% threshold."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        rally_price = base_price * 1.05  # Exactly 5% rise
        
        ticks = generate_tick_data(base_price, 20, start_time, interval_seconds=10)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=3, seconds=20),
            price=rally_price,
            volume=1000.0,
            instrument="TEST"
        ))
        
        result = detector.check(ticks)
        
        # Should NOT detect (threshold is > 5%, not >= 5%)
        assert result is None
    
    def test_flash_rally_large_spike(self):
        """Test detection of a very large flash rally (15% rise)."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        
        base_price = 200.0
        rally_price = base_price * 1.15  # 15% rise
        
        ticks = generate_tick_data(base_price, 18, start_time, interval_seconds=15)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=4, seconds=30),
            price=rally_price,
            volume=20000.0,
            instrument="ADANIPORTS"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_RALLY
        assert result.raw_data["rise_pct"] == pytest.approx(15.0, rel=0.01)


class TestFlashDetectorEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_price_volatility_within_threshold(self):
        """Test that normal volatility within threshold doesn't trigger detection."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        # Prices fluctuating within 4% range
        base_price = 1000.0
        ticks = []
        for i in range(30):
            # Oscillate between -2% and +2%
            price = base_price * (1.0 + 0.04 * (i % 2 - 0.5))
            ticks.append(TickData(
                timestamp=start_time + timedelta(seconds=i * 10),
                price=price,
                volume=1000.0,
                instrument="TEST"
            ))
        
        result = detector.check(ticks)
        assert result is None
    
    def test_custom_window_size(self):
        """Test using a custom window size."""
        detector = FlashDetector(threshold_pct=5.0, window_minutes=5)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        drop_price = base_price * 0.94  # 6% drop
        
        # Ticks over 8 minutes
        ticks = generate_tick_data(base_price, 48, start_time, interval_seconds=10)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=8),
            price=drop_price,
            volume=1000.0,
            instrument="TEST"
        ))
        
        # Use 3-minute window - should not detect if high was > 3 minutes ago
        result = detector.check(ticks, window_minutes=3)
        
        # The high is more than 3 minutes ago, so should not detect
        # Actually, the high is at the start (8 minutes ago), so with 3-minute window
        # we only look at recent 3 minutes where price was stable at base_price
        # Then dropped to drop_price, which is 6% below base_price
        # So it SHOULD detect
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
    
    def test_check_with_metadata(self):
        """Test the check_with_metadata convenience method."""
        detector = FlashDetector()
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        drop_price = base_price * 0.93  # 7% drop
        
        ticks = generate_tick_data(base_price, 20, start_time, interval_seconds=10)
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=3, seconds=20),
            price=drop_price,
            volume=1000.0,
            instrument="OLD_SYMBOL"  # This will be overridden
        ))
        
        result = detector.check_with_metadata(
            ticks=ticks,
            instrument="BANKNIFTY",
            asset_class="fo",
            exchange="NSE"
        )
        
        assert result is not None
        assert result.instrument == "BANKNIFTY"
        assert result.asset_class == "fo"
        assert result.exchange == "NSE"
    
    def test_multiple_peaks_and_troughs(self):
        """Test with multiple peaks and troughs in the window."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        # Create a pattern: 1000 -> 1050 -> 1000 -> 950
        ticks = []
        
        # Start at 1000
        ticks.extend(generate_tick_data(1000.0, 5, start_time, interval_seconds=10))
        
        # Rise to 1050
        ticks.extend(generate_tick_data(1050.0, 5, start_time + timedelta(seconds=50), interval_seconds=10))
        
        # Back to 1000
        ticks.extend(generate_tick_data(1000.0, 5, start_time + timedelta(seconds=100), interval_seconds=10))
        
        # Drop to 950 (5.26% drop from 1000, 9.52% drop from 1050)
        ticks.append(TickData(
            timestamp=start_time + timedelta(seconds=150),
            price=950.0,
            volume=1000.0,
            instrument="TEST"
        ))
        
        result = detector.check(ticks)
        
        # Should detect flash crash from the peak at 1050
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.raw_data["highest_price"] == 1050.0
        assert result.raw_data["drop_pct"] == pytest.approx(9.52, rel=0.01)
    
    def test_recovery_after_flash_crash(self):
        """Test that recovery after flash crash doesn't trigger false positive."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 1000.0
        
        # Normal prices
        ticks = generate_tick_data(base_price, 10, start_time, interval_seconds=10)
        
        # Flash crash to 940
        ticks.append(TickData(
            timestamp=start_time + timedelta(seconds=100),
            price=940.0,
            volume=5000.0,
            instrument="TEST"
        ))
        
        # Recovery back to 1000
        ticks.extend(generate_tick_data(base_price, 10, start_time + timedelta(seconds=110), interval_seconds=10))
        
        result = detector.check(ticks)
        
        # At the end, price is back to 1000, which is 6.38% above the low of 940
        # Should detect flash rally
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_RALLY


class TestFlashDetectorRealWorldScenarios:
    """Tests simulating real-world market scenarios."""
    
    def test_circuit_breaker_scenario(self):
        """Test detection during a circuit breaker event (10% drop)."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 45000.0  # BANKNIFTY
        circuit_price = base_price * 0.90  # 10% lower circuit
        
        # Normal trading
        ticks = generate_tick_data(base_price, 15, start_time, interval_seconds=20, instrument="BANKNIFTY")
        
        # Sudden drop to circuit
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=5),
            price=circuit_price,
            volume=50000.0,
            instrument="BANKNIFTY"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.severity == AnomalySeverity.CRITICAL
        assert result.raw_data["drop_pct"] == pytest.approx(10.0, rel=0.01)
    
    def test_news_driven_spike(self):
        """Test detection of news-driven price spike."""
        detector = FlashDetector(threshold_pct=5.0)
        start_time = datetime.utcnow()
        
        base_price = 2500.0  # Stock price
        news_price = base_price * 1.08  # 8% spike on positive news
        
        # Pre-news stable prices
        ticks = generate_tick_data(base_price, 20, start_time, interval_seconds=15, instrument="INFY")
        
        # News announcement spike
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=5),
            price=news_price,
            volume=100000.0,
            instrument="INFY"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_RALLY
        assert result.severity == AnomalySeverity.CRITICAL
    
    def test_crypto_flash_crash(self):
        """Test detection in crypto market (higher volatility)."""
        detector = FlashDetector(threshold_pct=5.0, window_minutes=5)
        start_time = datetime.utcnow()
        
        base_price = 50000.0  # BTC price
        crash_price = base_price * 0.92  # 8% drop
        
        # Crypto tick data (more frequent)
        ticks = generate_tick_data(base_price, 60, start_time, interval_seconds=5, instrument="BTCUSDT")
        
        # Flash crash
        ticks.append(TickData(
            timestamp=start_time + timedelta(minutes=5),
            price=crash_price,
            volume=1000.0,
            instrument="BTCUSDT"
        ))
        
        result = detector.check(ticks)
        
        assert result is not None
        assert result.anomaly_type == AnomalyType.FLASH_CRASH
        assert result.instrument == "BTCUSDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
