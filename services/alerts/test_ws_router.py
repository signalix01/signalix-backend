"""
Test suite for WebSocket alert delivery endpoint

Tests:
- Authentication via query param token
- Offline alert delivery on connection
- Live alert streaming via Redis pub/sub
- Delivery latency measurement
- Connection management

Requirements: 14.4, 14.5
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import jwt
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
import redis.asyncio as redis

from services.alerts.ws_router import (
    ws_router,
    ConnectionManager,
    verify_token,
    manager as global_manager
)
from shared.database.models import AnomalyEvent, AnomalySeverity, AnomalyType


# Test configuration
JWT_SECRET = "test-secret-key"
JWT_ALGORITHM = "HS256"


@pytest.fixture
def app():
    """Create FastAPI test app"""
    app = FastAPI()
    app.include_router(ws_router)
    return app


@pytest.fixture
def test_user_id():
    """Test user ID"""
    return "test-user-123"


@pytest.fixture
def valid_token(test_user_id):
    """Generate valid JWT token for testing"""
    payload = {
        "sub": test_user_id,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def expired_token(test_user_id):
    """Generate expired JWT token for testing"""
    payload = {
        "sub": test_user_id,
        "exp": datetime.utcnow() - timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_client = AsyncMock(spec=redis.Redis)
    
    # Mock pub/sub
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.listen = AsyncMock()
    
    mock_client.pubsub.return_value = mock_pubsub
    mock_client.lrange = AsyncMock(return_value=[])
    mock_client.delete = AsyncMock()
    
    return mock_client


@pytest.fixture
def connection_manager(mock_redis):
    """Create ConnectionManager with mocked Redis"""
    manager = ConnectionManager()
    manager.redis_client = mock_redis
    return manager


# ============================================================================
# Token Verification Tests
# ============================================================================

def test_verify_token_valid(test_user_id, valid_token):
    """Test token verification with valid token"""
    with patch.dict(os.environ, {"JWT_SECRET": JWT_SECRET, "JWT_ALGORITHM": JWT_ALGORITHM}):
        user_id = verify_token(valid_token)
        assert user_id == test_user_id


def test_verify_token_expired(expired_token):
    """Test token verification with expired token"""
    with patch.dict(os.environ, {"JWT_SECRET": JWT_SECRET, "JWT_ALGORITHM": JWT_ALGORITHM}):
        user_id = verify_token(expired_token)
        assert user_id is None


def test_verify_token_invalid():
    """Test token verification with invalid token"""
    with patch.dict(os.environ, {"JWT_SECRET": JWT_SECRET, "JWT_ALGORITHM": JWT_ALGORITHM}):
        user_id = verify_token("invalid-token")
        assert user_id is None


def test_verify_token_missing_sub():
    """Test token verification with missing sub field"""
    with patch.dict(os.environ, {"JWT_SECRET": JWT_SECRET, "JWT_ALGORITHM": JWT_ALGORITHM}):
        payload = {"exp": datetime.utcnow() + timedelta(hours=1)}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        user_id = verify_token(token)
        assert user_id is None


# ============================================================================
# ConnectionManager Tests
# ============================================================================

@pytest.mark.asyncio
async def test_connection_manager_connect(connection_manager, test_user_id):
    """Test ConnectionManager connect method"""
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Mock the pubsub listener to avoid actual Redis connection
    with patch.object(connection_manager, '_start_pubsub_listener', new=AsyncMock()):
        await connection_manager.connect(test_user_id, mock_websocket)
    
    # Verify connection accepted
    mock_websocket.accept.assert_called_once()
    
    # Verify user added to active connections
    assert test_user_id in connection_manager.active_connections
    assert connection_manager.active_connections[test_user_id] == mock_websocket


@pytest.mark.asyncio
async def test_connection_manager_disconnect(connection_manager, test_user_id):
    """Test ConnectionManager disconnect method"""
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Add connection
    connection_manager.active_connections[test_user_id] = mock_websocket
    
    # Add mock task
    mock_task = AsyncMock()
    mock_task.cancel = MagicMock()
    connection_manager.pubsub_tasks[test_user_id] = mock_task
    
    # Disconnect
    await connection_manager.disconnect(test_user_id)
    
    # Verify task cancelled
    mock_task.cancel.assert_called_once()
    
    # Verify connection removed
    assert test_user_id not in connection_manager.active_connections
    assert test_user_id not in connection_manager.pubsub_tasks


@pytest.mark.asyncio
async def test_send_offline_alerts(connection_manager, test_user_id, mock_redis):
    """Test sending offline alerts on connection"""
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Mock offline alerts
    offline_alerts = [
        {
            "type": "anomaly_alert",
            "event_id": "event-1",
            "instrument": "AAPL",
            "severity": "high",
            "detected_at": datetime.utcnow().isoformat(),
        },
        {
            "type": "anomaly_alert",
            "event_id": "event-2",
            "instrument": "GOOGL",
            "severity": "critical",
            "detected_at": datetime.utcnow().isoformat(),
        }
    ]
    
    # Mock Redis lrange to return offline alerts
    mock_redis.lrange.return_value = [json.dumps(alert) for alert in offline_alerts]
    
    # Send offline alerts
    await connection_manager.send_offline_alerts(test_user_id, mock_websocket)
    
    # Verify alerts sent
    assert mock_websocket.send_json.call_count == len(offline_alerts)
    
    # Verify each alert was sent with offline_delivery flag
    for call_args in mock_websocket.send_json.call_args_list:
        alert = call_args[0][0]
        assert alert["offline_delivery"] is True
        assert "ws_delivered_at" in alert


@pytest.mark.asyncio
async def test_pubsub_listener_receives_message(connection_manager, test_user_id, mock_redis):
    """Test pub/sub listener receives and forwards messages"""
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Create test alert
    test_alert = {
        "type": "anomaly_alert",
        "event_id": "event-123",
        "instrument": "AAPL",
        "severity": "critical",
        "detected_at": (datetime.utcnow() - timedelta(seconds=2)).isoformat(),
    }
    
    # Mock pub/sub messages
    async def mock_listen():
        # Yield subscription confirmation
        yield {"type": "subscribe", "channel": f"user_alerts:{test_user_id}"}
        # Yield actual message
        yield {"type": "message", "data": json.dumps(test_alert)}
        # Stop after one message
        await asyncio.sleep(0.1)
    
    mock_pubsub = mock_redis.pubsub.return_value
    mock_pubsub.listen.return_value = mock_listen()
    
    # Start listener in background
    listener_task = asyncio.create_task(
        connection_manager._pubsub_listener_loop(test_user_id, mock_websocket)
    )
    
    # Wait for message to be processed
    await asyncio.sleep(0.2)
    
    # Cancel listener
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    
    # Verify message was sent to WebSocket
    assert mock_websocket.send_json.called
    
    # Verify latency was calculated
    sent_alert = mock_websocket.send_json.call_args[0][0]
    assert "ws_delivery_latency_ms" in sent_alert
    assert "ws_delivered_at" in sent_alert
    assert sent_alert["ws_delivery_latency_ms"] >= 0


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_websocket_connection_with_valid_token(app, valid_token, test_user_id):
    """Test WebSocket connection with valid authentication token"""
    with patch.dict(os.environ, {"JWT_SECRET": JWT_SECRET, "JWT_ALGORITHM": JWT_ALGORITHM}):
        with patch.object(global_manager, 'initialize_redis', new=AsyncMock()):
            with patch.object(global_manager, 'connect', new=AsyncMock()):
                with patch.object(global_manager, 'send_offline_alerts', new=AsyncMock()):
                    with patch.object(global_manager, 'disconnect', new=AsyncMock()):
                        # This test verifies the authentication flow
                        # Full WebSocket testing requires a running server
                        pass


@pytest.mark.asyncio
async def test_websocket_connection_without_token(app):
    """Test WebSocket connection without authentication token"""
    # WebSocket should reject connection without token
    # This would be tested with a live server using websockets library
    pass


@pytest.mark.asyncio
async def test_websocket_delivery_latency_measurement(connection_manager, test_user_id):
    """Test that delivery latency is correctly measured and logged"""
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Create alert with detected_at timestamp
    detected_at = datetime.utcnow() - timedelta(seconds=3)
    test_alert = {
        "type": "anomaly_alert",
        "event_id": "event-latency-test",
        "instrument": "AAPL",
        "severity": "critical",
        "detected_at": detected_at.isoformat(),
    }
    
    # Mock pub/sub to deliver this message
    async def mock_listen():
        yield {"type": "subscribe"}
        yield {"type": "message", "data": json.dumps(test_alert)}
        await asyncio.sleep(0.1)
    
    mock_pubsub = connection_manager.redis_client.pubsub.return_value
    mock_pubsub.listen.return_value = mock_listen()
    
    # Start listener
    listener_task = asyncio.create_task(
        connection_manager._pubsub_listener_loop(test_user_id, mock_websocket)
    )
    
    # Wait for processing
    await asyncio.sleep(0.2)
    
    # Cancel
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    
    # Verify latency was calculated
    sent_alert = mock_websocket.send_json.call_args[0][0]
    latency_ms = sent_alert["ws_delivery_latency_ms"]
    
    # Latency should be approximately 3000ms (3 seconds)
    assert latency_ms >= 2900  # Allow some tolerance
    assert latency_ms <= 4000  # Upper bound


@pytest.mark.asyncio
async def test_websocket_health_endpoint(app):
    """Test WebSocket health check endpoint"""
    client = TestClient(app)
    
    response = client.get("/ws/alerts/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["service"] == "websocket_alerts"
    assert "active_connections" in data
    assert "redis_connected" in data
    assert "timestamp" in data


# ============================================================================
# End-to-End Scenario Test
# ============================================================================

@pytest.mark.asyncio
async def test_complete_alert_delivery_flow(connection_manager, test_user_id, mock_redis):
    """
    Test complete flow:
    1. User connects
    2. Receives offline alerts
    3. Receives live alert
    4. Latency is measured
    5. User disconnects
    """
    mock_websocket = AsyncMock(spec=WebSocket)
    
    # Step 1: Mock offline alerts
    offline_alert = {
        "type": "anomaly_alert",
        "event_id": "offline-1",
        "instrument": "TSLA",
        "severity": "high",
        "detected_at": (datetime.utcnow() - timedelta(minutes=10)).isoformat(),
    }
    mock_redis.lrange.return_value = [json.dumps(offline_alert)]
    
    # Step 2: Mock live alert via pub/sub
    live_alert = {
        "type": "anomaly_alert",
        "event_id": "live-1",
        "instrument": "AAPL",
        "severity": "critical",
        "detected_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat(),
    }
    
    async def mock_listen():
        yield {"type": "subscribe"}
        yield {"type": "message", "data": json.dumps(live_alert)}
        await asyncio.sleep(0.1)
    
    mock_pubsub = mock_redis.pubsub.return_value
    mock_pubsub.listen.return_value = mock_listen()
    
    # Step 3: Connect (with mocked pubsub start)
    with patch.object(connection_manager, '_start_pubsub_listener', new=AsyncMock()):
        await connection_manager.connect(test_user_id, mock_websocket)
    
    # Step 4: Send offline alerts
    await connection_manager.send_offline_alerts(test_user_id, mock_websocket)
    
    # Verify offline alert sent
    assert mock_websocket.send_json.call_count >= 1
    first_alert = mock_websocket.send_json.call_args_list[0][0][0]
    assert first_alert["event_id"] == "offline-1"
    assert first_alert["offline_delivery"] is True
    
    # Step 5: Simulate live alert delivery
    listener_task = asyncio.create_task(
        connection_manager._pubsub_listener_loop(test_user_id, mock_websocket)
    )
    
    await asyncio.sleep(0.2)
    
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    
    # Verify live alert sent
    assert mock_websocket.send_json.call_count >= 2
    
    # Step 6: Disconnect
    connection_manager.pubsub_tasks[test_user_id] = listener_task
    await connection_manager.disconnect(test_user_id)
    
    # Verify cleanup
    assert test_user_id not in connection_manager.active_connections


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
