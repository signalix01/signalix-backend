"""
Unit tests for Alert Matching Engine

Tests all matching logic including:
- Instrument filter matching
- Asset class filter matching
- Anomaly type filter matching
- Severity filter matching
- Quiet hours check (IST timezone)
- Rate limit check (Redis counter)
- CRITICAL severity bypass

Requirements: 13.2, 13.3, 13.4, 13.5
Task: 39
"""

import pytest
import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch
import pytz
import uuid

from services.alerts.matcher import AlertMatcher
from shared.database.models import AlertRule, AnomalyEvent, AnomalySeverity, AnomalyType


@pytest.fixture
def matcher():
    """Create an AlertMatcher instance for testing"""
    return AlertMatcher()


@pytest.fixture
def sample_event():
    """Create a sample anomaly event for testing"""
    return AnomalyEvent(
        id=uuid.uuid4(),
        instrument="BANKNIFTY",
        asset_class="fo",
        exchange="NSE",
        anomaly_type=AnomalyType.FLASH_CRASH,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Flash crash detected",
        z_score=4.5,
        price=45000.0,
        volume=1000000.0
    )


@pytest.fixture
def sample_rule():
    """Create a sample alert rule for testing"""
    return AlertRule(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test Rule",
        description="Test alert rule",
        instruments=["BANKNIFTY"],
        asset_classes=["fo"],
        anomaly_types=["flash_crash", "flash_rally"],
        min_severity=AnomalySeverity.MEDIUM,
        channels=["in_app", "push"],
        max_alerts_per_hour=10,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
        enabled=True
    )


class TestInstrumentMatching:
    """Test instrument filter matching"""
    
    def test_matches_specific_instrument(self, matcher, sample_event, sample_rule):
        """Test matching with specific instrument"""
        sample_rule.instruments = ["BANKNIFTY"]
        assert matcher._matches_instrument_filter(sample_event, sample_rule) is True
    
    def test_does_not_match_different_instrument(self, matcher, sample_event, sample_rule):
        """Test non-matching with different instrument"""
        sample_rule.instruments = ["NIFTY"]
        assert matcher._matches_instrument_filter(sample_event, sample_rule) is False
    
    def test_matches_all_instruments(self, matcher, sample_event, sample_rule):
        """Test matching with ALL wildcard"""
        sample_rule.instruments = ["ALL"]
        assert matcher._matches_instrument_filter(sample_event, sample_rule) is True
    
    def test_matches_multiple_instruments(self, matcher, sample_event, sample_rule):
        """Test matching with multiple instruments in list"""
        sample_rule.instruments = ["NIFTY", "BANKNIFTY", "SENSEX"]
        assert matcher._matches_instrument_filter(sample_event, sample_rule) is True


class TestAssetClassMatching:
    """Test asset class filter matching"""
    
    def test_matches_asset_class(self, matcher, sample_event, sample_rule):
        """Test matching asset class"""
        sample_rule.asset_classes = ["fo"]
        assert matcher._matches_asset_class_filter(sample_event, sample_rule) is True
    
    def test_does_not_match_different_asset_class(self, matcher, sample_event, sample_rule):
        """Test non-matching asset class"""
        sample_rule.asset_classes = ["equity"]
        assert matcher._matches_asset_class_filter(sample_event, sample_rule) is False
    
    def test_matches_multiple_asset_classes(self, matcher, sample_event, sample_rule):
        """Test matching with multiple asset classes"""
        sample_rule.asset_classes = ["equity", "fo", "crypto"]
        assert matcher._matches_asset_class_filter(sample_event, sample_rule) is True


class TestAnomalyTypeMatching:
    """Test anomaly type filter matching"""
    
    def test_matches_anomaly_type(self, matcher, sample_event, sample_rule):
        """Test matching anomaly type"""
        sample_rule.anomaly_types = ["flash_crash"]
        assert matcher._matches_anomaly_type_filter(sample_event, sample_rule) is True
    
    def test_does_not_match_different_anomaly_type(self, matcher, sample_event, sample_rule):
        """Test non-matching anomaly type"""
        sample_rule.anomaly_types = ["volume_surge"]
        assert matcher._matches_anomaly_type_filter(sample_event, sample_rule) is False
    
    def test_matches_multiple_anomaly_types(self, matcher, sample_event, sample_rule):
        """Test matching with multiple anomaly types"""
        sample_rule.anomaly_types = ["flash_crash", "flash_rally", "whale_movement"]
        assert matcher._matches_anomaly_type_filter(sample_event, sample_rule) is True


class TestSeverityMatching:
    """Test severity filter matching"""
    
    def test_matches_exact_severity(self, matcher, sample_event, sample_rule):
        """Test matching with exact severity"""
        sample_event.severity = AnomalySeverity.HIGH
        sample_rule.min_severity = AnomalySeverity.HIGH
        assert matcher._matches_severity_filter(sample_event, sample_rule) is True
    
    def test_matches_higher_severity(self, matcher, sample_event, sample_rule):
        """Test matching with higher severity than minimum"""
        sample_event.severity = AnomalySeverity.CRITICAL
        sample_rule.min_severity = AnomalySeverity.MEDIUM
        assert matcher._matches_severity_filter(sample_event, sample_rule) is True
    
    def test_does_not_match_lower_severity(self, matcher, sample_event, sample_rule):
        """Test non-matching with lower severity than minimum"""
        sample_event.severity = AnomalySeverity.LOW
        sample_rule.min_severity = AnomalySeverity.HIGH
        assert matcher._matches_severity_filter(sample_event, sample_rule) is False
    
    def test_severity_hierarchy(self, matcher, sample_event, sample_rule):
        """Test complete severity hierarchy: LOW < MEDIUM < HIGH < CRITICAL"""
        # LOW does not match MEDIUM
        sample_event.severity = AnomalySeverity.LOW
        sample_rule.min_severity = AnomalySeverity.MEDIUM
        assert matcher._matches_severity_filter(sample_event, sample_rule) is False
        
        # MEDIUM matches MEDIUM
        sample_event.severity = AnomalySeverity.MEDIUM
        sample_rule.min_severity = AnomalySeverity.MEDIUM
        assert matcher._matches_severity_filter(sample_event, sample_rule) is True
        
        # HIGH matches MEDIUM
        sample_event.severity = AnomalySeverity.HIGH
        sample_rule.min_severity = AnomalySeverity.MEDIUM
        assert matcher._matches_severity_filter(sample_event, sample_rule) is True
        
        # CRITICAL matches MEDIUM
        sample_event.severity = AnomalySeverity.CRITICAL
        sample_rule.min_severity = AnomalySeverity.MEDIUM
        assert matcher._matches_severity_filter(sample_event, sample_rule) is True


class TestQuietHours:
    """Test quiet hours checking with IST timezone"""
    
    def test_no_quiet_hours_configured(self, matcher, sample_rule):
        """Test when no quiet hours are configured"""
        sample_rule.quiet_hours_start = None
        sample_rule.quiet_hours_end = None
        assert matcher._is_in_quiet_hours(sample_rule) is False
    
    def test_in_quiet_hours_same_day(self, matcher, sample_rule):
        """Test quiet hours within same day (e.g., 08:00 to 18:00)"""
        sample_rule.quiet_hours_start = "08:00"
        sample_rule.quiet_hours_end = "18:00"
        
        # Create IST datetime at 12:00 (noon) - should be in quiet hours
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        
        assert matcher._is_in_quiet_hours(sample_rule, test_time) is True
    
    def test_not_in_quiet_hours_same_day(self, matcher, sample_rule):
        """Test outside quiet hours within same day"""
        sample_rule.quiet_hours_start = "08:00"
        sample_rule.quiet_hours_end = "18:00"
        
        # Create IST datetime at 20:00 (8 PM) - should NOT be in quiet hours
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 20, 0, 0))
        
        assert matcher._is_in_quiet_hours(sample_rule, test_time) is False
    
    def test_in_quiet_hours_spanning_midnight(self, matcher, sample_rule):
        """Test quiet hours spanning midnight (e.g., 22:00 to 08:00)"""
        sample_rule.quiet_hours_start = "22:00"
        sample_rule.quiet_hours_end = "08:00"
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        
        # Test at 23:00 (11 PM) - should be in quiet hours
        test_time_night = ist_tz.localize(datetime(2024, 1, 15, 23, 0, 0))
        assert matcher._is_in_quiet_hours(sample_rule, test_time_night) is True
        
        # Test at 06:00 (6 AM) - should be in quiet hours
        test_time_morning = ist_tz.localize(datetime(2024, 1, 15, 6, 0, 0))
        assert matcher._is_in_quiet_hours(sample_rule, test_time_morning) is True
        
        # Test at 12:00 (noon) - should NOT be in quiet hours
        test_time_noon = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        assert matcher._is_in_quiet_hours(sample_rule, test_time_noon) is False
    
    def test_quiet_hours_boundary_start(self, matcher, sample_rule):
        """Test exact start time of quiet hours"""
        sample_rule.quiet_hours_start = "22:00"
        sample_rule.quiet_hours_end = "08:00"
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 22, 0, 0))
        
        assert matcher._is_in_quiet_hours(sample_rule, test_time) is True
    
    def test_quiet_hours_boundary_end(self, matcher, sample_rule):
        """Test exact end time of quiet hours"""
        sample_rule.quiet_hours_start = "22:00"
        sample_rule.quiet_hours_end = "08:00"
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 8, 0, 0))
        
        assert matcher._is_in_quiet_hours(sample_rule, test_time) is True
    
    def test_utc_to_ist_conversion(self, matcher, sample_rule):
        """Test UTC to IST timezone conversion"""
        sample_rule.quiet_hours_start = "22:00"
        sample_rule.quiet_hours_end = "08:00"
        
        # Create UTC datetime at 18:00 UTC (which is 23:30 IST)
        # IST is UTC+5:30
        utc_time = pytz.utc.localize(datetime(2024, 1, 15, 18, 0, 0))
        
        # 18:00 UTC = 23:30 IST, which should be in quiet hours (22:00-08:00)
        assert matcher._is_in_quiet_hours(sample_rule, utc_time) is True


class TestRateLimiting:
    """Test rate limiting with Redis counter"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_not_exceeded(self, matcher, sample_rule):
        """Test when rate limit is not exceeded"""
        # Mock Redis client
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="5")  # 5 alerts sent
        
        sample_rule.max_alerts_per_hour = 10
        
        result = await matcher._check_rate_limit("test-user-id", sample_rule)
        assert result is False  # Not exceeded
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, matcher, sample_rule):
        """Test when rate limit is exceeded"""
        # Mock Redis client
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="10")  # 10 alerts sent
        
        sample_rule.max_alerts_per_hour = 10
        
        result = await matcher._check_rate_limit("test-user-id", sample_rule)
        assert result is True  # Exceeded
    
    @pytest.mark.asyncio
    async def test_rate_limit_no_previous_alerts(self, matcher, sample_rule):
        """Test when no alerts have been sent this hour"""
        # Mock Redis client
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value=None)  # No previous alerts
        
        sample_rule.max_alerts_per_hour = 10
        
        result = await matcher._check_rate_limit("test-user-id", sample_rule)
        assert result is False  # Not exceeded
    
    @pytest.mark.asyncio
    async def test_rate_limit_increment(self, matcher):
        """Test incrementing rate counter"""
        # Mock Redis client
        matcher._redis_client = AsyncMock()
        matcher._redis_client.incr = AsyncMock(return_value=1)
        matcher._redis_client.expire = AsyncMock()
        
        await matcher._increment_rate_counter("test-user-id")
        
        # Verify incr was called
        matcher._redis_client.incr.assert_called_once()
        
        # Verify expire was called with 3600 seconds (1 hour)
        matcher._redis_client.expire.assert_called_once()
        call_args = matcher._redis_client.expire.call_args
        assert call_args[0][1] == 3600
    
    @pytest.mark.asyncio
    async def test_rate_limit_error_handling(self, matcher, sample_rule):
        """Test rate limit check fails gracefully on error"""
        # Mock Redis client to raise exception
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        
        sample_rule.max_alerts_per_hour = 10
        
        # Should return False (fail open) on error
        result = await matcher._check_rate_limit("test-user-id", sample_rule)
        assert result is False


class TestFindMatchingRules:
    """Test the main find_matching_rules method"""
    
    @pytest.mark.asyncio
    async def test_find_matching_rules_basic(self, matcher, sample_event, sample_rule):
        """Test finding matching rules with basic filters"""
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Mock Redis for rate limiting
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="0")
        matcher._redis_client.incr = AsyncMock()
        matcher._redis_client.expire = AsyncMock()
        
        # Set time outside quiet hours (12:00 IST)
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        
        # Find matching rules
        matching_rules = await matcher.find_matching_rules(sample_event, test_time)
        
        assert len(matching_rules) == 1
        assert matching_rules[0].id == sample_rule.id
    
    @pytest.mark.asyncio
    async def test_critical_bypasses_quiet_hours(self, matcher, sample_event, sample_rule):
        """Test CRITICAL severity bypasses quiet hours"""
        # Set event to CRITICAL
        sample_event.severity = AnomalySeverity.CRITICAL
        
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Mock Redis (not needed for CRITICAL, but set up anyway)
        matcher._redis_client = AsyncMock()
        
        # Set time INSIDE quiet hours (23:00 IST)
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 23, 0, 0))
        
        # Find matching rules - should match despite quiet hours
        matching_rules = await matcher.find_matching_rules(sample_event, test_time)
        
        assert len(matching_rules) == 1
        assert matching_rules[0].id == sample_rule.id
    
    @pytest.mark.asyncio
    async def test_critical_bypasses_rate_limit(self, matcher, sample_event, sample_rule):
        """Test CRITICAL severity bypasses rate limits"""
        # Set event to CRITICAL
        sample_event.severity = AnomalySeverity.CRITICAL
        
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Mock Redis with rate limit exceeded
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="100")  # Way over limit
        
        # Set time outside quiet hours
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        
        # Find matching rules - should match despite rate limit
        matching_rules = await matcher.find_matching_rules(sample_event, test_time)
        
        assert len(matching_rules) == 1
        assert matching_rules[0].id == sample_rule.id
    
    @pytest.mark.asyncio
    async def test_non_critical_blocked_by_quiet_hours(self, matcher, sample_event, sample_rule):
        """Test non-CRITICAL events are blocked by quiet hours"""
        # Set event to HIGH (not CRITICAL)
        sample_event.severity = AnomalySeverity.HIGH
        
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Mock Redis
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="0")
        
        # Set time INSIDE quiet hours (23:00 IST)
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 23, 0, 0))
        
        # Find matching rules - should NOT match due to quiet hours
        matching_rules = await matcher.find_matching_rules(sample_event, test_time)
        
        assert len(matching_rules) == 0
    
    @pytest.mark.asyncio
    async def test_non_critical_blocked_by_rate_limit(self, matcher, sample_event, sample_rule):
        """Test non-CRITICAL events are blocked by rate limits"""
        # Set event to HIGH (not CRITICAL)
        sample_event.severity = AnomalySeverity.HIGH
        
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Mock Redis with rate limit exceeded
        matcher._redis_client = AsyncMock()
        matcher._redis_client.get = AsyncMock(return_value="10")  # At limit
        
        sample_rule.max_alerts_per_hour = 10
        
        # Set time outside quiet hours
        ist_tz = pytz.timezone('Asia/Kolkata')
        test_time = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        
        # Find matching rules - should NOT match due to rate limit
        matching_rules = await matcher.find_matching_rules(sample_event, test_time)
        
        assert len(matching_rules) == 0
    
    @pytest.mark.asyncio
    async def test_disabled_rule_not_matched(self, matcher, sample_event, sample_rule):
        """Test disabled rules are not matched"""
        # Disable the rule
        sample_rule.enabled = False
        
        # Mock database session to return disabled rule
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # Query filters out disabled
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        matcher._async_session_maker = MagicMock(return_value=mock_session)
        
        # Find matching rules - should be empty
        matching_rules = await matcher.find_matching_rules(sample_event)
        
        assert len(matching_rules) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
