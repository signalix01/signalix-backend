"""
Tests for Anomaly Event Deduplication Service

Requirements: 11.8
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.alerts.deduplication import DedupService, get_dedup_service
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


@pytest.fixture
def dedup_service():
    """Create a deduplication service instance for testing"""
    service = DedupService()
    
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()
    mock_redis.delete = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=900)
    mock_redis.close = AsyncMock()
    
    service._client = mock_redis
    
    return service


@pytest.fixture
def sample_event():
    """Create a sample anomaly event"""
    return AnomalyEvent(
        id=uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Price spike detected",
        z_score=3.5,
        price=2500.0,
        volume=1000000.0
    )


class TestDedupService:
    """Test suite for DedupService"""
    
    def test_get_dedup_key(self, dedup_service):
        """Test dedup key generation"""
        key = dedup_service._get_dedup_key("RELIANCE", "price_spike")
        assert key == "dedup:RELIANCE:price_spike"
        
        key = dedup_service._get_dedup_key("BTCUSDT", "volume_surge")
        assert key == "dedup:BTCUSDT:volume_surge"
    
    def test_severity_ordering(self, dedup_service):
        """Test severity level ordering"""
        assert dedup_service.SEVERITY_ORDER[AnomalySeverity.LOW] == 1
        assert dedup_service.SEVERITY_ORDER[AnomalySeverity.MEDIUM] == 2
        assert dedup_service.SEVERITY_ORDER[AnomalySeverity.HIGH] == 3
        assert dedup_service.SEVERITY_ORDER[AnomalySeverity.CRITICAL] == 4
    
    def test_is_severity_increase_true(self, dedup_service):
        """Test severity increase detection - positive cases"""
        # Medium → High
        assert dedup_service._is_severity_increase("medium", AnomalySeverity.HIGH) is True
        
        # Low → Medium
        assert dedup_service._is_severity_increase("low", AnomalySeverity.MEDIUM) is True
        
        # Medium → Critical
        assert dedup_service._is_severity_increase("medium", AnomalySeverity.CRITICAL) is True
        
        # Low → Critical
        assert dedup_service._is_severity_increase("low", AnomalySeverity.CRITICAL) is True
    
    def test_is_severity_increase_false(self, dedup_service):
        """Test severity increase detection - negative cases"""
        # Same severity
        assert dedup_service._is_severity_increase("medium", AnomalySeverity.MEDIUM) is False
        
        # Decrease
        assert dedup_service._is_severity_increase("high", AnomalySeverity.MEDIUM) is False
        assert dedup_service._is_severity_increase("critical", AnomalySeverity.HIGH) is False
        assert dedup_service._is_severity_increase("medium", AnomalySeverity.LOW) is False
    
    def test_is_severity_increase_invalid(self, dedup_service):
        """Test severity increase with invalid input - should fail open"""
        # Invalid previous severity - should return True (fail open)
        assert dedup_service._is_severity_increase("invalid", AnomalySeverity.HIGH) is True
    
    @pytest.mark.asyncio
    async def test_should_suppress_no_recent_event(self, dedup_service, sample_event):
        """Test: No recent event exists - should NOT suppress"""
        # Mock: No existing event in Redis
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is False  # Should NOT suppress
        
        # Verify event was stored
        dedup_service._client.hset.assert_called_once()
        dedup_service._client.expire.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_should_suppress_same_severity(self, dedup_service, sample_event):
        """Test: Recent event with same severity - SHOULD suppress"""
        # Mock: Existing event with same severity
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'medium',
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
        })
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is True  # SHOULD suppress
        
        # Verify event was NOT stored (suppressed)
        dedup_service._client.hset.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_should_suppress_lower_severity(self, dedup_service, sample_event):
        """Test: Recent event with higher severity, new event lower - SHOULD suppress"""
        # Mock: Existing event with HIGH severity
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'high',
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
        })
        
        # New event with MEDIUM severity
        sample_event.severity = AnomalySeverity.MEDIUM
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is True  # SHOULD suppress
    
    @pytest.mark.asyncio
    async def test_should_suppress_severity_escalation(self, dedup_service, sample_event):
        """Test: Severity escalation (medium → high) - should NOT suppress"""
        # Mock: Existing event with MEDIUM severity
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'medium',
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
        })
        
        # New event with HIGH severity (escalation)
        sample_event.severity = AnomalySeverity.HIGH
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is False  # Should NOT suppress (escalation)
        
        # Verify event was stored with new severity
        dedup_service._client.hset.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_should_suppress_critical_escalation(self, dedup_service, sample_event):
        """Test: Escalation to CRITICAL - should NOT suppress"""
        # Mock: Existing event with HIGH severity
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'high',
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
        })
        
        # New event with CRITICAL severity
        sample_event.severity = AnomalySeverity.CRITICAL
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is False  # Should NOT suppress
    
    @pytest.mark.asyncio
    async def test_should_suppress_malformed_data(self, dedup_service, sample_event):
        """Test: Malformed Redis data - should fail open (not suppress)"""
        # Mock: Malformed data (missing severity)
        dedup_service._client.hgetall = AsyncMock(return_value={
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
            # Missing 'severity' field
        })
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is False  # Should NOT suppress (fail open)
    
    @pytest.mark.asyncio
    async def test_should_suppress_redis_error(self, dedup_service, sample_event):
        """Test: Redis error - should fail open (not suppress)"""
        # Mock: Redis error
        dedup_service._client.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await dedup_service.should_suppress(sample_event)
        
        assert result is False  # Should NOT suppress (fail open on error)
    
    @pytest.mark.asyncio
    async def test_store_event(self, dedup_service, sample_event):
        """Test event storage in Redis"""
        await dedup_service._store_event(sample_event)
        
        # Verify hset was called with correct key
        call_args = dedup_service._client.hset.call_args
        assert call_args is not None
        
        key = call_args[0][0]
        assert key == "dedup:RELIANCE:price_spike"
        
        # Verify data contains severity
        data = call_args[1]['mapping']
        assert data['severity'] == 'medium'
        assert 'detected_at' in data
        assert 'event_id' in data
        
        # Verify TTL was set
        dedup_service._client.expire.assert_called_once_with(
            "dedup:RELIANCE:price_spike",
            900  # 15 minutes
        )
    
    @pytest.mark.asyncio
    async def test_clear_dedup_state(self, dedup_service):
        """Test clearing deduplication state"""
        await dedup_service.clear_dedup_state("RELIANCE", "price_spike")
        
        dedup_service._client.delete.assert_called_once_with(
            "dedup:RELIANCE:price_spike"
        )
    
    @pytest.mark.asyncio
    async def test_get_dedup_state(self, dedup_service):
        """Test getting deduplication state"""
        # Mock: Existing state
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'high',
            'detected_at': datetime.utcnow().isoformat(),
            'event_id': str(uuid4())
        })
        dedup_service._client.ttl = AsyncMock(return_value=600)
        
        state = await dedup_service.get_dedup_state("RELIANCE", "price_spike")
        
        assert state is not None
        assert state['severity'] == 'high'
        assert state['ttl_seconds'] == 600
    
    @pytest.mark.asyncio
    async def test_get_dedup_state_not_found(self, dedup_service):
        """Test getting deduplication state when not found"""
        # Mock: No state
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        state = await dedup_service.get_dedup_state("RELIANCE", "price_spike")
        
        assert state is None


class TestDedupServiceIntegration:
    """Integration tests for deduplication scenarios"""
    
    @pytest.mark.asyncio
    async def test_duplicate_event_within_window(self, dedup_service):
        """
        Test: Fire same event twice within 10 minutes - second should be suppressed
        
        Requirements: 11.8
        """
        # First event
        event1 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Price spike detected",
            z_score=3.5,
            price=2500.0
        )
        
        # Mock: No existing event
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        # First event should NOT be suppressed
        result1 = await dedup_service.should_suppress(event1)
        assert result1 is False
        
        # Second event (same type, same instrument, 10 minutes later)
        event2 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow() + timedelta(minutes=10),
            description="Price spike detected again",
            z_score=3.6,
            price=2520.0
        )
        
        # Mock: Existing event from first call
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'medium',
            'detected_at': event1.detected_at.isoformat(),
            'event_id': str(event1.id)
        })
        
        # Second event SHOULD be suppressed
        result2 = await dedup_service.should_suppress(event2)
        assert result2 is True
    
    @pytest.mark.asyncio
    async def test_severity_escalation_not_suppressed(self, dedup_service):
        """
        Test: Fire high severity after medium - should NOT be suppressed
        
        Requirements: 11.8
        """
        # First event with MEDIUM severity
        event1 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Price spike detected",
            z_score=3.5,
            price=2500.0
        )
        
        # Mock: No existing event
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        # First event should NOT be suppressed
        result1 = await dedup_service.should_suppress(event1)
        assert result1 is False
        
        # Second event with HIGH severity (escalation)
        event2 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.HIGH,
            detected_at=datetime.utcnow() + timedelta(minutes=5),
            description="Price spike intensified",
            z_score=4.5,
            price=2600.0
        )
        
        # Mock: Existing event with MEDIUM severity
        dedup_service._client.hgetall = AsyncMock(return_value={
            'severity': 'medium',
            'detected_at': event1.detected_at.isoformat(),
            'event_id': str(event1.id)
        })
        
        # Second event should NOT be suppressed (severity escalation)
        result2 = await dedup_service.should_suppress(event2)
        assert result2 is False
    
    @pytest.mark.asyncio
    async def test_different_instruments_not_deduplicated(self, dedup_service):
        """Test: Same anomaly type on different instruments - should NOT deduplicate"""
        # Event on RELIANCE
        event1 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Price spike on RELIANCE",
            z_score=3.5,
            price=2500.0
        )
        
        # Event on TCS (different instrument)
        event2 = AnomalyEvent(
            id=uuid4(),
            instrument="TCS",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Price spike on TCS",
            z_score=3.5,
            price=3500.0
        )
        
        # Mock: No existing events
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        # Both events should NOT be suppressed (different instruments)
        result1 = await dedup_service.should_suppress(event1)
        result2 = await dedup_service.should_suppress(event2)
        
        assert result1 is False
        assert result2 is False
    
    @pytest.mark.asyncio
    async def test_different_anomaly_types_not_deduplicated(self, dedup_service):
        """Test: Different anomaly types on same instrument - should NOT deduplicate"""
        # Price spike event
        event1 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Price spike",
            z_score=3.5,
            price=2500.0
        )
        
        # Volume surge event (different type)
        event2 = AnomalyEvent(
            id=uuid4(),
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.VOLUME_SURGE,
            severity=AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow(),
            description="Volume surge",
            z_score=3.5,
            volume=5000000.0
        )
        
        # Mock: No existing events
        dedup_service._client.hgetall = AsyncMock(return_value={})
        
        # Both events should NOT be suppressed (different anomaly types)
        result1 = await dedup_service.should_suppress(event1)
        result2 = await dedup_service.should_suppress(event2)
        
        assert result1 is False
        assert result2 is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
