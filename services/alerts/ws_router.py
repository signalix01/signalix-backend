"""
Real-Time Alert WebSocket Endpoint
Delivers alerts to connected clients via WebSocket with offline queueing support

Requirements: 14.4, 14.5
"""
import logging
import asyncio
import json
from typing import Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect, Query, status
from fastapi.routing import APIRouter
import redis.asyncio as redis
import jwt
from jwt.exceptions import InvalidTokenError
import os

from services.alerts.channels.in_app import InAppChannel

logger = logging.getLogger(__name__)

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET", "prod-super-secret-key-change-this-to-random-64-char-string-12345678"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Create router
ws_router = APIRouter()


class ConnectionManager:
    """
    Manages active WebSocket connections for alert delivery.
    Tracks connected users and handles pub/sub subscriptions.
    """
    
    def __init__(self):
        """Initialize connection manager"""
        self.active_connections: dict[str, WebSocket] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub_tasks: dict[str, asyncio.Task] = {}
        self._redis_initialized = False
    
    async def initialize_redis(self):
        """Initialize Redis connection"""
        if self._redis_initialized:
            return
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            await self.redis_client.ping()
            self._redis_initialized = True
            logger.info("ConnectionManager: Redis initialized")
        except Exception as e:
            logger.warning(f"ConnectionManager: Redis not available ({e}), running without pub/sub")
            self.redis_client = None
            self._redis_initialized = True
    
    async def connect(self, user_id: str, websocket: WebSocket):
        """
        Accept WebSocket connection and set up Redis pub/sub
        
        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        # Disconnect previous connection for same user (avoid duplicates)
        if user_id in self.active_connections:
            old_ws = self.active_connections[user_id]
            try:
                await old_ws.close()
            except Exception:
                pass
            await self.disconnect(user_id)
            
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"WebSocket connected for user {user_id}")
        
        # Start Redis pub/sub listener for this user (only if Redis is available)
        if self.redis_client is not None:
            await self._start_pubsub_listener(user_id, websocket)
    
    async def disconnect(self, user_id: str):
        """
        Remove WebSocket connection and clean up pub/sub
        
        Args:
            user_id: User ID
        """
        # Cancel pub/sub task
        task = self.pubsub_tasks.pop(user_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        
        # Remove connection
        self.active_connections.pop(user_id, None)
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    async def _start_pubsub_listener(self, user_id: str, websocket: WebSocket):
        """
        Start Redis pub/sub listener for user alerts
        
        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        # Create pub/sub task
        task = asyncio.create_task(
            self._pubsub_listener_loop(user_id, websocket)
        )
        self.pubsub_tasks[user_id] = task
    
    async def _pubsub_listener_loop(self, user_id: str, websocket: WebSocket):
        """
        Listen to Redis pub/sub channel and forward messages to WebSocket
        
        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        channel = f"user_alerts:{user_id}"
        
        try:
            # Create pub/sub connection
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")
            
            # Listen for messages
            async for message in pubsub.listen():
                if message["type"] == "message":
                    payload = message["data"]
                    
                    # Parse and enrich with delivery timestamp
                    try:
                        alert_data = json.loads(payload)
                        
                        # Calculate delivery latency
                        if "detected_at" in alert_data:
                            detected_at = datetime.fromisoformat(alert_data["detected_at"])
                            now = datetime.utcnow()
                            latency_ms = int((now - detected_at).total_seconds() * 1000)
                            alert_data["ws_delivery_latency_ms"] = latency_ms
                            
                            # Log latency
                            logger.info(
                                f"WebSocket delivery latency for user {user_id}: {latency_ms}ms "
                                f"(event: {alert_data.get('event_id', 'unknown')})"
                            )
                        
                        # Add WebSocket delivery timestamp
                        alert_data["ws_delivered_at"] = datetime.utcnow().isoformat()
                        
                        # Send to WebSocket
                        await websocket.send_json(alert_data)
                        logger.debug(f"Sent alert to user {user_id} via WebSocket")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse alert payload: {e}")
                    except Exception as e:
                        logger.error(f"Error sending alert to WebSocket: {e}")
                        # Connection might be broken, let the main loop handle it
                        break
        
        except asyncio.CancelledError:
            logger.info(f"Pub/sub listener cancelled for user {user_id}")
            raise
        
        except Exception as e:
            logger.error(f"Error in pub/sub listener for user {user_id}: {e}", exc_info=True)
        
        finally:
            # Clean up pub/sub connection
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                logger.info(f"Unsubscribed from Redis channel: {channel}")
            except Exception as e:
                logger.error(f"Error closing pub/sub connection: {e}")
    
    async def send_offline_alerts(self, user_id: str, websocket: WebSocket):
        """
        Send queued offline alerts to newly connected user
        
        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        try:
            # Get offline alerts from InAppChannel
            in_app_channel = InAppChannel(self.redis_client)
            offline_alerts = await in_app_channel.get_offline_alerts(user_id)
            
            if offline_alerts:
                logger.info(f"Delivering {len(offline_alerts)} offline alerts to user {user_id}")
                
                # Send each offline alert
                for alert in offline_alerts:
                    # Mark as offline delivery
                    alert["offline_delivery"] = True
                    alert["ws_delivered_at"] = datetime.utcnow().isoformat()
                    
                    await websocket.send_json(alert)
                    
                    # Small delay to avoid overwhelming client
                    await asyncio.sleep(0.1)
                
                logger.info(f"Successfully delivered {len(offline_alerts)} offline alerts to user {user_id}")
            else:
                logger.debug(f"No offline alerts for user {user_id}")
        
        except Exception as e:
            logger.error(f"Error sending offline alerts to user {user_id}: {e}", exc_info=True)


# Global connection manager instance
manager = ConnectionManager()


def verify_token(token: str) -> Optional[str]:
    """
    Verify JWT token and extract user_id
    
    Args:
        token: JWT token string
        
    Returns:
        User ID if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        
        if user_id is None:
            logger.warning("Token payload missing 'sub' field")
            return None
        
        return user_id
    
    except InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None
    
    except Exception as e:
        logger.error(f"Error verifying token: {e}", exc_info=True)
        return None


@ws_router.websocket("/ws/alerts")
async def websocket_alerts_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time alert delivery
    
    **Authentication**: Provide JWT token as query parameter
    
    **Flow**:
    1. Client connects with valid token
    2. Server delivers any queued offline alerts
    3. Server streams live alerts from Redis pub/sub
    4. On disconnect, alerts are queued for next connection
    
    **Message Format**:
    ```json
    {
        "type": "anomaly_alert",
        "rule_id": "uuid",
        "event_id": "uuid",
        "instrument": "AAPL",
        "asset_class": "equity",
        "anomaly_type": "price_spike",
        "severity": "critical",
        "description": "Price spiked 5.2% in 5 minutes",
        "detected_at": "2024-01-15T10:30:00Z",
        "price": 150.25,
        "volume": 1000000,
        "z_score": 3.5,
        "affected_instruments": ["AAPL"],
        "ws_delivery_latency_ms": 1234,
        "ws_delivered_at": "2024-01-15T10:30:01.234Z",
        "offline_delivery": false
    }
    ```
    
    **Requirements**: 14.4, 14.5
    """
    # Initialize Redis if not already done
    if manager.redis_client is None:
        await manager.initialize_redis()
    
    # Verify authentication token
    user_id = verify_token(token)
    
    if user_id is None:
        logger.warning("WebSocket connection rejected: invalid token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return
    
    try:
        # Accept connection and set up pub/sub
        await manager.connect(user_id, websocket)
        
        # Send queued offline alerts first (only if Redis is available)
        if manager.redis_client is not None:
            await manager.send_offline_alerts(user_id, websocket)
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong, subscription updates, etc.)
                data = await websocket.receive_text()
                
                # Handle client messages
                try:
                    message = json.loads(data)
                    message_type = message.get("type")
                    
                    if message_type == "ping":
                        # Respond to ping
                        await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
                    
                    elif message_type == "subscribe":
                        # Client wants to update subscription (future enhancement)
                        logger.info(f"User {user_id} sent subscribe message: {message}")
                        await websocket.send_json({
                            "type": "ack",
                            "message": "Subscription updates not yet implemented"
                        })
                    
                    else:
                        logger.warning(f"Unknown message type from user {user_id}: {message_type}")
                
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from user {user_id}: {data}")
            
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {user_id}")
                break
            
            except Exception as e:
                logger.error(f"Error in WebSocket loop for user {user_id}: {e}", exc_info=True)
                break
    
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint for user {user_id}: {e}", exc_info=True)
    
    finally:
        # Clean up connection
        await manager.disconnect(user_id)


@ws_router.get("/ws/alerts/health")
async def websocket_health():
    """
    Health check endpoint for WebSocket service
    
    Returns:
        dict with service status and active connections count
    """
    return {
        "status": "healthy",
        "service": "websocket_alerts",
        "active_connections": len(manager.active_connections),
        "redis_connected": manager.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }
