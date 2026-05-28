"""
In-App Alert Channel
Publishes alerts to Redis pub/sub for WebSocket delivery

Requirements: 13.2, 13.6
"""
import json
import logging
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)


class InAppChannel:
    """
    In-app alert delivery via Redis pub/sub.
    WebSocket clients subscribe to user_alerts:{user_id} channel.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize in-app channel
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str) -> dict:
        """
        Publish alert to Redis pub/sub channel
        
        Args:
            user_id: User ID to send alert to
            event: AnomalyEvent instance
            rule_id: Alert rule ID that triggered this delivery
            
        Returns:
            dict with status and details
        """
        try:
            channel = f"user_alerts:{user_id}"
            
            # Format alert payload
            payload = {
                "type": "anomaly_alert",
                "rule_id": rule_id,
                "event_id": str(event.id),
                "instrument": event.instrument,
                "asset_class": event.asset_class,
                "anomaly_type": event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type),
                "severity": event.severity.value if hasattr(event.severity, 'value') else str(event.severity),
                "description": event.description,
                "detected_at": event.detected_at.isoformat() if event.detected_at else datetime.utcnow().isoformat(),
                "price": event.price,
                "volume": event.volume,
                "z_score": event.z_score,
                "affected_instruments": event.affected_instruments or [],
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Publish to Redis pub/sub
            subscribers = await self.redis.publish(channel, json.dumps(payload))
            
            # Also store in offline queue if no active subscribers
            if subscribers == 0:
                await self._queue_for_offline_delivery(user_id, payload)
                logger.info(f"No active subscribers for {channel}, queued for offline delivery")
            
            logger.info(f"Published in-app alert to {channel} (subscribers: {subscribers})")
            
            return {
                "status": "sent",
                "channel": "in_app",
                "subscribers": subscribers,
                "queued_offline": subscribers == 0,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send in-app alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "in_app",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    async def _queue_for_offline_delivery(self, user_id: str, payload: dict) -> None:
        """
        Queue alert for delivery when user reconnects
        
        Args:
            user_id: User ID
            payload: Alert payload
        """
        try:
            queue_key = f"offline_alerts:{user_id}"
            
            # Add to Redis list (max 100 items per user)
            await self.redis.lpush(queue_key, json.dumps(payload))
            await self.redis.ltrim(queue_key, 0, 99)  # Keep only latest 100
            
            # Set expiry: 7 days
            await self.redis.expire(queue_key, 7 * 24 * 60 * 60)
            
        except Exception as e:
            logger.error(f"Failed to queue offline alert: {str(e)}", exc_info=True)
    
    async def get_offline_alerts(self, user_id: str, limit: int = 100) -> list:
        """
        Retrieve queued offline alerts for a user
        
        Args:
            user_id: User ID
            limit: Maximum number of alerts to retrieve
            
        Returns:
            List of alert payloads
        """
        try:
            queue_key = f"offline_alerts:{user_id}"
            
            # Get all queued alerts
            raw_alerts = await self.redis.lrange(queue_key, 0, limit - 1)
            
            # Parse JSON
            alerts = [json.loads(alert) for alert in raw_alerts]
            
            # Clear the queue after retrieval
            await self.redis.delete(queue_key)
            
            logger.info(f"Retrieved {len(alerts)} offline alerts for user {user_id}")
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to retrieve offline alerts: {str(e)}", exc_info=True)
            return []
    
    async def send_test(self, user_id: str) -> dict:
        """
        Send a test alert
        
        Args:
            user_id: User ID to send test alert to
            
        Returns:
            dict with status and details
        """
        try:
            channel = f"user_alerts:{user_id}"
            
            payload = {
                "type": "test_alert",
                "message": "This is a test alert from Signalix",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            subscribers = await self.redis.publish(channel, json.dumps(payload))
            
            return {
                "status": "sent",
                "channel": "in_app",
                "subscribers": subscribers,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "in_app",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
