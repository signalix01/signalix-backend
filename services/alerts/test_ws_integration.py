"""
Integration test for WebSocket alert delivery
Tests the complete flow: anomaly detection -> Redis pub/sub -> WebSocket delivery

Requirements: 14.4, 14.5
"""
import pytest
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
import jwt

# Set test environment variables before importing modules
os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["REDIS_URL"] = "redis://localhost:6379"

from fastapi import FastAPI
from fastapi.testclient import TestClient
import redis.asyncio as redis

from services.alerts.ws_router import ws_router
from services.alerts.channels.in_app import InAppChannel
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
    return "test-user-integration-123"


@pytest.fixture
def valid_token(test_user_id):
    """Generate valid JWT token for testing"""
    payload = {
        "sub": test_user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def sample_anomaly_event():
    """Create sample anomaly event for testing"""
    return {
        "type": "anomaly_alert",
        "rule_id": "rule-123",
        "event_id": "event-456",
        "instrument": "AAPL",
        "asset_class": "equity",
        "anomaly_type": "price_spike",
        "severity": "critical",
        "description": "Price spiked 5.2% in 5 minutes - unusual volume detected",
        "detected_at": (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(),
        "price": 150.25,
        "volume": 1000000,
        "z_score": 3.5,
        "affected_instruments": ["AAPL"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_websocket_receives_alert_under_5_seconds(
    app, test_user_id, valid_token, sample_anomaly_event
):
    """
    Test that WebSocket receives alert within 5 seconds of detection
    
    This is the key requirement from task 42:
    "Write test: connect WebSocket, trigger anomaly, verify message received in < 5 seconds"
    
    Requirements: 14.4, 14.5
    """
    # Mock Redis to avoid actual connection
    mock_redis_client = AsyncMock(spec=redis.Redis)
    
    # Track messages sent
    messages_received = []
    
    # Mock pub/sub
    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0
        
        def __aiter__(self):
            return self
        
        async def __anext__(self):
            if self.index >= len(self.items):
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            if self.index == 2:  # After subscription, wait a bit
                await asyncio.sleep(0.5)
            return item
    
    messages = [
        {"type": "subscribe", "channel": f"user_alerts:{test_user_id}"},
        {"type": "message", "data": json.dumps(sample_anomaly_event)}
    ]
    
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=MockAsyncIterator(messages))
    
    mock_redis_client.pubsub.return_value = mock_pubsub
    mock_redis_client.lrange = AsyncMock(return_value=[])  # No offline alerts
    mock_redis_client.delete = AsyncMock()
    
    # Patch Redis connection
    with patch('redis.asyncio.from_url', return_value=mock_redis_client):
        # Import manager after patching
        from services.alerts.ws_router import manager
        
        # Mock WebSocket
        mock_websocket = AsyncMock()
        
        # Track when messages are sent
        async def track_send_json(data):
            messages_received.append({
                "data": data,
                "timestamp": datetime.now(timezone.utc)
            })
        
        mock_websocket.send_json = track_send_json
        mock_websocket.accept = AsyncMock()
        
        # Initialize Redis
        await manager.initialize_redis()
        
        # Connect WebSocket
        await manager.connect(test_user_id, mock_websocket)
        
        # Send offline alerts (should be none)
        await manager.send_offline_alerts(test_user_id, mock_websocket)
        
        # Wait for pub/sub message to be delivered
        await asyncio.sleep(1.0)
        
        # Disconnect
        await manager.disconnect(test_user_id)
        
        # Verify alert was received
        assert len(messages_received) > 0, "No messages received"
        
        # Verify the alert content
        alert = messages_received[0]["data"]
        assert alert["event_id"] == sample_anomaly_event["event_id"]
        assert alert["instrument"] == sample_anomaly_event["instrument"]
        assert alert["severity"] == sample_anomaly_event["severity"]
        
        # Verify latency was calculated
        assert "ws_delivery_latency_ms" in alert
        assert "ws_delivered_at" in alert
        
        # Verify latency is under 5 seconds (5000ms)
        latency_ms = alert["ws_delivery_latency_ms"]
        assert latency_ms < 5000, f"Latency {latency_ms}ms exceeds 5 second requirement"
        
        print(f"✓ Alert delivered in {latency_ms}ms (requirement: < 5000ms)")


@pytest.mark.asyncio
async def test_offline_alerts_delivered_on_connection(
    app, test_user_id, valid_token
):
    """
    Test that offline alerts are delivered when user reconnects
    
    Requirements: 14.4
    """
    # Create offline alerts
    offline_alerts = [
        {
            "type": "anomaly_alert",
            "event_id": "offline-1",
            "instrument": "TSLA",
            "severity": "high",
            "detected_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        },
        {
            "type": "anomaly_alert",
            "event_id": "offline-2",
            "instrument": "GOOGL",
            "severity": "critical",
            "detected_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }
    ]
    
    # Mock Redis
    mock_redis_client = AsyncMock(spec=redis.Redis)
    mock_redis_client.lrange = AsyncMock(
        return_value=[json.dumps(alert) for alert in offline_alerts]
    )
    mock_redis_client.delete = AsyncMock()
    
    # Mock pub/sub (no live messages)
    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0
        
        def __aiter__(self):
            return self
        
        async def __anext__(self):
            if self.index >= len(self.items):
                await asyncio.sleep(0.1)
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            return item
    
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=MockAsyncIterator([{"type": "subscribe"}]))
    
    mock_redis_client.pubsub.return_value = mock_pubsub
    
    # Patch Redis
    with patch('redis.asyncio.from_url', return_value=mock_redis_client):
        from services.alerts.ws_router import manager
        
        # Mock WebSocket
        messages_received = []
        
        async def track_send_json(data):
            messages_received.append(data)
        
        mock_websocket = AsyncMock()
        mock_websocket.send_json = track_send_json
        mock_websocket.accept = AsyncMock()
        
        # Initialize and connect
        await manager.initialize_redis()
        await manager.connect(test_user_id, mock_websocket)
        
        # Send offline alerts
        await manager.send_offline_alerts(test_user_id, mock_websocket)
        
        # Wait a bit
        await asyncio.sleep(0.3)
        
        # Disconnect
        await manager.disconnect(test_user_id)
        
        # Verify offline alerts were delivered
        assert len(messages_received) == len(offline_alerts), \
            f"Expected {len(offline_alerts)} offline alerts, got {len(messages_received)}"
        
        # Verify each alert has offline_delivery flag
        for msg in messages_received:
            assert msg["offline_delivery"] is True
            assert "ws_delivered_at" in msg
        
        # Verify Redis queue was cleared
        mock_redis_client.delete.assert_called()
        
        print(f"✓ Delivered {len(messages_received)} offline alerts on reconnection")


@pytest.mark.asyncio
async def test_latency_measurement_accuracy(test_user_id):
    """
    Test that delivery latency is accurately measured
    
    Requirements: 14.5
    """
    # Mock Redis
    mock_redis_client = AsyncMock(spec=redis.Redis)
    
    # Create alert with known detection time
    detection_time = datetime.now(timezone.utc) - timedelta(seconds=3)
    test_alert = {
        "type": "anomaly_alert",
        "event_id": "latency-test",
        "instrument": "AAPL",
        "severity": "critical",
        "detected_at": detection_time.isoformat(),
    }
    
    # Mock pub/sub
    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0
        
        def __aiter__(self):
            return self
        
        async def __anext__(self):
            if self.index >= len(self.items):
                await asyncio.sleep(0.1)
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            return item
    
    messages = [
        {"type": "subscribe"},
        {"type": "message", "data": json.dumps(test_alert)}
    ]
    
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=MockAsyncIterator(messages))
    
    mock_redis_client.pubsub.return_value = mock_pubsub
    mock_redis_client.lrange = AsyncMock(return_value=[])
    
    # Patch Redis
    with patch('redis.asyncio.from_url', return_value=mock_redis_client):
        from services.alerts.ws_router import manager
        
        # Mock WebSocket
        messages_received = []
        
        async def track_send_json(data):
            messages_received.append(data)
        
        mock_websocket = AsyncMock()
        mock_websocket.send_json = track_send_json
        mock_websocket.accept = AsyncMock()
        
        # Initialize and connect
        await manager.initialize_redis()
        await manager.connect(test_user_id, mock_websocket)
        
        # Wait for message
        await asyncio.sleep(0.3)
        
        # Disconnect
        await manager.disconnect(test_user_id)
        
        # Verify latency measurement
        assert len(messages_received) > 0
        alert = messages_received[0]
        
        latency_ms = alert["ws_delivery_latency_ms"]
        
        # Latency should be approximately 3000ms (3 seconds)
        # Allow tolerance of ±500ms
        assert 2500 <= latency_ms <= 3500, \
            f"Latency {latency_ms}ms not in expected range (2500-3500ms)"
        
        print(f"✓ Latency measurement accurate: {latency_ms}ms (expected ~3000ms)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
