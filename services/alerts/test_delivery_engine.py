"""
Integration tests for AlertDeliveryEngine

Tests:
- Trigger event and verify delivery logged for all channels
- Verify retry on first failure
- Verify concurrent delivery for CRITICAL alerts
- Verify sequential delivery for non-critical alerts
- Verify offline queue for in-app channel

Requirements: 13.2, 14.1, 14.2, 14.3, 14.4
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
import redis.asyncio as redis
import os

from services.alerts.delivery_engine import AlertDeliveryEngine
from shared.database.models import (
    AnomalyEvent,
    AlertRule,
    AlertDeliveryLog,
    AnomalyType,
    AnomalySeverity,
    Base
)


# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test"
)

# Test Redis URL
TEST_REDIS_URL = os.getenv(
    "TEST_REDIS_URL",
    "redis://localhost:6379/1"
)


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def test_engine(event_loop):
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables synchronously
    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    event_loop.run_until_complete(setup())
    
    yield engine
    
    # Drop tables synchronously
    async def teardown():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
    
    event_loop.run_until_complete(teardown())


@pytest.fixture
async def db_session(test_engine):
    """Create database session for tests"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def redis_client():
    """Create Redis client for tests"""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    
    yield client
    
    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def sample_event(db_session):
    """Create a sample anomaly event"""
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Price spike detected: +5.2% in 5 minutes",
        z_score=3.5,
        price=2450.50,
        volume=1500000,
        affected_instruments=["RELIANCE", "NIFTY"],
        raw_data={"change_pct": 5.2, "timeframe": "5m"}
    )
    
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    
    yield event
    
    # Cleanup
    await db_session.delete(event)
    await db_session.commit()


@pytest.fixture
async def sample_rule(db_session):
    """Create a sample alert rule"""
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test Alert Rule",
        description="Test rule for integration testing",
        instruments=["RELIANCE"],
        asset_classes=["equity"],
        anomaly_types=["price_spike"],
        min_severity=AnomalySeverity.MEDIUM,
        channels=["in_app", "email"],
        max_alerts_per_hour=10,
        enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    
    yield rule
    
    # Cleanup
    await db_session.delete(rule)
    await db_session.commit()


@pytest.mark.asyncio
async def test_deliver_to_all_channels(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Trigger event, verify delivery logged for all channels
    
    Requirements: 13.2, 14.3
    """
    # Create delivery engine
    engine = AlertDeliveryEngine(db_session, redis_client)
    
    # Mock channel send methods to return success
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.return_value = {
            "status": "sent",
            "channel": "in_app",
            "subscribers": 1,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        mock_email.return_value = {
            "status": "sent",
            "channel": "email",
            "to": "test@example.com",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify delivery summary
        assert result["rules_matched"] == 1
        assert result["deliveries_attempted"] == 2  # in_app + email
        assert result["deliveries_successful"] == 2
        assert result["deliveries_failed"] == 0
        
        # Verify channels were called
        assert mock_in_app.called
        assert mock_email.called
        
        # Verify delivery logs were created
        logs = await db_session.execute(
            select(AlertDeliveryLog).where(
                AlertDeliveryLog.anomaly_event_id == sample_event.id
            )
        )
        logs = logs.scalars().all()
        
        assert len(logs) >= 2  # At least 2 logs (one per channel)
        
        # Verify log details
        channels_logged = {log.channel for log in logs}
        assert "in_app" in channels_logged
        assert "email" in channels_logged
        
        # Verify all successful
        for log in logs:
            if log.status != "skipped":  # Email might be skipped if no address configured
                assert log.status in ["sent", "pending"]
                assert log.attempt_number >= 1


@pytest.mark.asyncio
async def test_retry_on_failure(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify retry on first failure
    
    Requirements: 14.2
    """
    # Create delivery engine with faster retry delays for testing
    engine = AlertDeliveryEngine(db_session, redis_client)
    engine.retry_delays = [0.1, 0.2, 0.3]  # Fast retries for testing
    
    # Mock channel to fail first, then succeed
    call_count = 0
    
    async def mock_send_with_retry(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        if call_count == 1:
            # First attempt fails
            return {
                "status": "failed",
                "channel": "in_app",
                "error": "Connection timeout",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Second attempt succeeds
            return {
                "status": "sent",
                "channel": "in_app",
                "subscribers": 1,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.side_effect = mock_send_with_retry
        mock_email.return_value = {
            "status": "sent",
            "channel": "email",
            "to": "test@example.com",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify retry happened
        assert call_count == 2  # First attempt + 1 retry
        
        # Verify delivery logs show retry attempts
        logs = await db_session.execute(
            select(AlertDeliveryLog).where(
                AlertDeliveryLog.anomaly_event_id == sample_event.id,
                AlertDeliveryLog.channel == "in_app"
            ).order_by(AlertDeliveryLog.attempt_number)
        )
        logs = logs.scalars().all()
        
        # Should have at least 2 log entries (failed attempt + successful retry)
        assert len(logs) >= 2
        
        # First attempt should be failed
        assert logs[0].attempt_number == 1
        assert logs[0].status == "failed"
        assert logs[0].error_message is not None
        
        # Second attempt should be successful
        assert logs[1].attempt_number == 2
        assert logs[1].status in ["sent", "pending"]


@pytest.mark.asyncio
async def test_critical_concurrent_delivery(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify concurrent delivery for CRITICAL alerts
    
    Requirements: 14.1
    """
    # Make event CRITICAL
    sample_event.severity = AnomalySeverity.CRITICAL
    await db_session.commit()
    
    # Create delivery engine
    engine = AlertDeliveryEngine(db_session, redis_client)
    
    # Track call order to verify concurrency
    call_times = []
    
    async def mock_send_with_delay(channel_name):
        async def _send(*args, **kwargs):
            call_times.append((channel_name, datetime.utcnow()))
            await asyncio.sleep(0.1)  # Simulate API call
            return {
                "status": "sent",
                "channel": channel_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        return _send
    
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.side_effect = await mock_send_with_delay("in_app")
        mock_email.side_effect = await mock_send_with_delay("email")
        
        # Deliver alert
        start_time = datetime.utcnow()
        result = await engine.deliver(sample_event, [sample_rule])
        end_time = datetime.utcnow()
        
        # Verify both channels were called
        assert len(call_times) == 2
        
        # Verify calls happened concurrently (within 50ms of each other)
        time_diff = abs((call_times[1][1] - call_times[0][1]).total_seconds())
        assert time_diff < 0.05, f"Calls should be concurrent, but were {time_diff}s apart"
        
        # Verify total time is close to single call time (not sum of both)
        total_time = (end_time - start_time).total_seconds()
        assert total_time < 0.3, f"Concurrent delivery should be fast, took {total_time}s"


@pytest.mark.asyncio
async def test_non_critical_sequential_delivery(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify sequential delivery for non-critical alerts
    
    Requirements: 14.1
    """
    # Make event non-critical (HIGH, not CRITICAL)
    sample_event.severity = AnomalySeverity.HIGH
    await db_session.commit()
    
    # Create delivery engine
    engine = AlertDeliveryEngine(db_session, redis_client)
    
    # Track call order
    call_order = []
    
    async def mock_send_with_tracking(channel_name):
        async def _send(*args, **kwargs):
            call_order.append(channel_name)
            await asyncio.sleep(0.05)  # Simulate API call
            return {
                "status": "sent",
                "channel": channel_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        return _send
    
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.side_effect = await mock_send_with_tracking("in_app")
        mock_email.side_effect = await mock_send_with_tracking("email")
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify both channels were called in order
        assert len(call_order) == 2
        assert call_order == ["in_app", "email"]  # Sequential order


@pytest.mark.asyncio
async def test_offline_queue(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify offline queue for in-app channel
    
    Requirements: 14.4
    """
    # Create delivery engine
    engine = AlertDeliveryEngine(db_session, redis_client)
    
    # Mock in_app channel to return 0 subscribers (user offline)
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app:
        mock_in_app.return_value = {
            "status": "sent",
            "channel": "in_app",
            "subscribers": 0,  # No active subscribers
            "queued_offline": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify in_app channel was called
        assert mock_in_app.called
        
        # Verify offline queue was populated
        user_id = str(sample_rule.user_id)
        queue_key = f"offline_alerts:{user_id}"
        
        queue_length = await redis_client.llen(queue_key)
        assert queue_length > 0, "Offline queue should have at least one alert"
        
        # Verify queue content
        queued_alert = await redis_client.lindex(queue_key, 0)
        assert queued_alert is not None
        
        # Parse and verify alert data
        import json
        alert_data = json.loads(queued_alert)
        assert alert_data["type"] == "anomaly_alert"
        assert alert_data["event_id"] == str(sample_event.id)


@pytest.mark.asyncio
async def test_max_retries_exhausted(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify behavior when all retries are exhausted
    
    Requirements: 14.2
    """
    # Create delivery engine with fast retries
    engine = AlertDeliveryEngine(db_session, redis_client)
    engine.retry_delays = [0.05, 0.05, 0.05]  # Fast retries for testing
    
    # Mock channel to always fail
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.return_value = {
            "status": "failed",
            "channel": "in_app",
            "error": "Connection refused",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        mock_email.return_value = {
            "status": "sent",
            "channel": "email",
            "to": "test@example.com",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify in_app failed after retries
        assert result["deliveries_failed"] >= 1
        
        # Verify all retry attempts were logged
        logs = await db_session.execute(
            select(AlertDeliveryLog).where(
                AlertDeliveryLog.anomaly_event_id == sample_event.id,
                AlertDeliveryLog.channel == "in_app"
            ).order_by(AlertDeliveryLog.attempt_number)
        )
        logs = logs.scalars().all()
        
        # Should have 3 attempts (initial + 2 retries, or max_retries)
        assert len(logs) >= 3
        
        # All attempts should be failed
        for log in logs:
            assert log.status == "failed"
            assert log.error_message is not None


@pytest.mark.asyncio
async def test_latency_tracking(db_session, redis_client, sample_event, sample_rule):
    """
    Test: Verify latency tracking from detection to delivery
    
    Requirements: 14.3
    """
    # Create delivery engine
    engine = AlertDeliveryEngine(db_session, redis_client)
    
    # Mock channel to return success
    with patch.object(engine.in_app_channel, 'send', new_callable=AsyncMock) as mock_in_app, \
         patch.object(engine.email_channel, 'send', new_callable=AsyncMock) as mock_email:
        
        mock_in_app.return_value = {
            "status": "sent",
            "channel": "in_app",
            "subscribers": 1,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        mock_email.return_value = {
            "status": "sent",
            "channel": "email",
            "to": "test@example.com",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Deliver alert
        result = await engine.deliver(sample_event, [sample_rule])
        
        # Verify delivery logs have latency tracking
        logs = await db_session.execute(
            select(AlertDeliveryLog).where(
                AlertDeliveryLog.anomaly_event_id == sample_event.id,
                AlertDeliveryLog.status == "sent"
            )
        )
        logs = logs.scalars().all()
        
        # At least one successful delivery should have latency tracked
        assert len(logs) > 0
        
        for log in logs:
            if log.detection_to_delivery_ms is not None:
                # Latency should be reasonable (< 10 seconds for test)
                assert log.detection_to_delivery_ms < 10000
                assert log.detection_to_delivery_ms >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
