"""
Tests for Alert History API Router

Task 43: Implement alert history API
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from datetime import datetime, timedelta
import uuid

from services.alerts.history_router import router
from shared.database.models import (
    Base,
    AnomalyEvent,
    AlertDeliveryLog,
    AlertRule,
    AnomalyType,
    AnomalySeverity,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool


# Test database setup
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test database session"""
    AsyncSessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
def app():
    """Create FastAPI test app"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
async def sample_events(test_session):
    """Create sample anomaly events for testing"""
    events = []
    
    # Create 5 sample events
    for i in range(5):
        event = AnomalyEvent(
            id=uuid.uuid4(),
            instrument=f"TEST{i}",
            asset_class="equity",
            exchange="NSE",
            anomaly_type=AnomalyType.PRICE_SPIKE if i % 2 == 0 else AnomalyType.VOLUME_SURGE,
            severity=AnomalySeverity.HIGH if i < 3 else AnomalySeverity.MEDIUM,
            detected_at=datetime.utcnow() - timedelta(hours=i),
            description=f"Test anomaly event {i}",
            z_score=3.5 + i * 0.1,
            price=100.0 + i * 10,
            volume=1000000 + i * 100000,
            raw_data={"test_data": f"value_{i}"},
        )
        test_session.add(event)
        events.append(event)
    
    await test_session.commit()
    
    # Refresh to get IDs
    for event in events:
        await test_session.refresh(event)
    
    return events


@pytest.fixture
async def sample_delivery_logs(test_session, sample_events):
    """Create sample delivery logs for testing"""
    # Create a sample alert rule first
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        name="Test Rule",
        description="Test alert rule",
        instruments=["TEST0", "TEST1"],
        asset_classes=["equity"],
        anomaly_types=["price_spike"],
        min_severity=AnomalySeverity.MEDIUM,
        channels=["in_app", "email"],
        enabled=True,
    )
    test_session.add(rule)
    await test_session.commit()
    await test_session.refresh(rule)
    
    logs = []
    
    # Create delivery logs for first 3 events
    for i, event in enumerate(sample_events[:3]):
        log = AlertDeliveryLog(
            id=uuid.uuid4(),
            anomaly_event_id=event.id,
            alert_rule_id=rule.id,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            channel="in_app" if i % 2 == 0 else "email",
            status="sent" if i < 2 else "failed",
            attempt_number=1,
            delivered_at=datetime.utcnow() if i < 2 else None,
            error_message=None if i < 2 else "Test error",
            detection_to_delivery_ms=1000 + i * 100,
            created_at=datetime.utcnow() - timedelta(hours=i),
        )
        test_session.add(log)
        logs.append(log)
    
    await test_session.commit()
    
    # Refresh to get IDs
    for log in logs:
        await test_session.refresh(log)
    
    return logs


# ============================================================================
# Tests for GET /api/v1/alerts/events
# ============================================================================

@pytest.mark.asyncio
async def test_get_anomaly_events_success(client, sample_events):
    """Test successful retrieval of anomaly events"""
    response = client.get("/api/v1/alerts/events")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "events" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    
    assert data["total"] == 5
    assert len(data["events"]) == 5
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_get_anomaly_events_pagination(client, sample_events):
    """Test pagination of anomaly events"""
    # Get first page with 2 items
    response = client.get("/api/v1/alerts/events?page=1&page_size=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 5
    assert len(data["events"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 3
    
    # Get second page
    response = client.get("/api/v1/alerts/events?page=2&page_size=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["events"]) == 2
    assert data["page"] == 2


@pytest.mark.asyncio
async def test_get_anomaly_events_filter_by_instrument(client, sample_events):
    """Test filtering anomaly events by instrument"""
    response = client.get("/api/v1/alerts/events?instrument=TEST0")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert len(data["events"]) == 1
    assert data["events"][0]["instrument"] == "TEST0"


@pytest.mark.asyncio
async def test_get_anomaly_events_filter_by_anomaly_type(client, sample_events):
    """Test filtering anomaly events by anomaly type"""
    response = client.get("/api/v1/alerts/events?anomaly_type=price_spike")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3  # Events 0, 2, 4
    for event in data["events"]:
        assert event["anomaly_type"] == "price_spike"


@pytest.mark.asyncio
async def test_get_anomaly_events_filter_by_severity(client, sample_events):
    """Test filtering anomaly events by severity"""
    response = client.get("/api/v1/alerts/events?severity=high")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3  # Events 0, 1, 2
    for event in data["events"]:
        assert event["severity"] == "high"


@pytest.mark.asyncio
async def test_get_anomaly_events_invalid_anomaly_type(client, sample_events):
    """Test error handling for invalid anomaly type"""
    response = client.get("/api/v1/alerts/events?anomaly_type=invalid_type")
    
    assert response.status_code == 400
    assert "Invalid anomaly_type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_anomaly_events_date_range(client, sample_events):
    """Test filtering anomaly events by date range"""
    # Get events from last 2 hours
    start_date = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    
    response = client.get(f"/api/v1/alerts/events?start_date={start_date}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should get events 0 and 1 (most recent)
    assert data["total"] >= 2


# ============================================================================
# Tests for GET /api/v1/alerts/events/{event_id}
# ============================================================================

@pytest.mark.asyncio
async def test_get_anomaly_event_detail_success(client, sample_events):
    """Test successful retrieval of anomaly event detail"""
    event_id = str(sample_events[0].id)
    
    response = client.get(f"/api/v1/alerts/events/{event_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == event_id
    assert data["instrument"] == "TEST0"
    assert "raw_data" in data
    assert data["raw_data"]["test_data"] == "value_0"


@pytest.mark.asyncio
async def test_get_anomaly_event_detail_not_found(client):
    """Test error handling for non-existent event"""
    fake_id = str(uuid.uuid4())
    
    response = client.get(f"/api/v1/alerts/events/{fake_id}")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_anomaly_event_detail_invalid_id(client):
    """Test error handling for invalid event ID format"""
    response = client.get("/api/v1/alerts/events/invalid-uuid")
    
    assert response.status_code == 400
    assert "Invalid event_id format" in response.json()["detail"]


# ============================================================================
# Tests for GET /api/v1/alerts/delivery-log
# ============================================================================

@pytest.mark.asyncio
async def test_get_delivery_log_success(client, sample_delivery_logs):
    """Test successful retrieval of delivery log"""
    response = client.get("/api/v1/alerts/delivery-log")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "logs" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    
    assert data["total"] == 3
    assert len(data["logs"]) == 3


@pytest.mark.asyncio
async def test_get_delivery_log_pagination(client, sample_delivery_logs):
    """Test pagination of delivery log"""
    response = client.get("/api/v1/alerts/delivery-log?page=1&page_size=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3
    assert len(data["logs"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2


@pytest.mark.asyncio
async def test_get_delivery_log_filter_by_channel(client, sample_delivery_logs):
    """Test filtering delivery log by channel"""
    response = client.get("/api/v1/alerts/delivery-log?channel=in_app")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2  # Logs 0 and 2
    for log in data["logs"]:
        assert log["channel"] == "in_app"


@pytest.mark.asyncio
async def test_get_delivery_log_filter_by_status(client, sample_delivery_logs):
    """Test filtering delivery log by status"""
    response = client.get("/api/v1/alerts/delivery-log?status=sent")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2  # Logs 0 and 1
    for log in data["logs"]:
        assert log["status"] == "sent"


@pytest.mark.asyncio
async def test_get_delivery_log_includes_event_details(client, sample_delivery_logs):
    """Test that delivery log includes event details"""
    response = client.get("/api/v1/alerts/delivery-log")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check first log has event details
    log = data["logs"][0]
    assert "instrument" in log
    assert "anomaly_type" in log
    assert "severity" in log
    assert "description" in log


# ============================================================================
# Tests for Health Check
# ============================================================================

@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/api/v1/alerts/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["service"] == "alert_history_api"
    assert "timestamp" in data


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_workflow(client, sample_events, sample_delivery_logs):
    """Test full workflow: list events, get detail, check delivery log"""
    # 1. List events
    response = client.get("/api/v1/alerts/events")
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) > 0
    
    # 2. Get detail of first event
    event_id = events[0]["id"]
    response = client.get(f"/api/v1/alerts/events/{event_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == event_id
    assert "raw_data" in detail
    
    # 3. Check delivery log
    response = client.get("/api/v1/alerts/delivery-log")
    assert response.status_code == 200
    logs = response.json()["logs"]
    assert len(logs) > 0
    
    # Verify log has event details
    assert logs[0]["instrument"] is not None
    assert logs[0]["anomaly_type"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
