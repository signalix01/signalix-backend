"""
Push Notification Channel
Sends push notifications via Firebase Cloud Messaging (FCM)

Requirements: 13.2, 13.6
"""
import logging
from typing import Optional
from datetime import datetime
import os
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)

# Firebase Admin SDK (lazy import to avoid dependency issues)
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("firebase-admin not installed, push notifications disabled")


class PushChannel:
    """
    Push notification delivery via Firebase Cloud Messaging (FCM).
    Sends to all registered device tokens for a user.
    """
    
    def __init__(self):
        """Initialize push notification channel"""
        self.initialized = False
        
        if FIREBASE_AVAILABLE:
            self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if already initialized
            if firebase_admin._apps:
                self.initialized = True
                logger.info("Firebase Admin SDK already initialized")
                return
            
            # Initialize from service account JSON
            firebase_creds_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
            
            if firebase_creds_path and os.path.exists(firebase_creds_path):
                cred = credentials.Certificate(firebase_creds_path)
                firebase_admin.initialize_app(cred)
                self.initialized = True
                logger.info("Firebase Admin SDK initialized successfully")
            else:
                logger.warning("Firebase service account not configured, push notifications disabled")
                
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}", exc_info=True)
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str, device_tokens: list[str]) -> dict:
        """
        Send push notification to user's devices
        
        Args:
            user_id: User ID
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            device_tokens: List of FCM device tokens
            
        Returns:
            dict with status and details
        """
        if not FIREBASE_AVAILABLE or not self.initialized:
            return {
                "status": "skipped",
                "channel": "push",
                "reason": "Firebase not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not device_tokens:
            return {
                "status": "skipped",
                "channel": "push",
                "reason": "No device tokens registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Format notification
            title = self._format_title(event)
            body = self._format_body(event)
            
            # Build FCM message
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={
                    "type": "anomaly_alert",
                    "rule_id": rule_id,
                    "event_id": str(event.id),
                    "instrument": event.instrument,
                    "anomaly_type": event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type),
                    "severity": event.severity.value if hasattr(event.severity, 'value') else str(event.severity),
                    "detected_at": event.detected_at.isoformat() if event.detected_at else "",
                },
                tokens=device_tokens,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        sound="default",
                        channel_id="anomaly_alerts",
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound="default",
                            badge=1,
                        ),
                    ),
                ),
            )
            
            # Send to FCM
            response = messaging.send_multicast(message)
            
            logger.info(f"Sent push notification: {response.success_count}/{len(device_tokens)} successful")
            
            return {
                "status": "sent",
                "channel": "push",
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "total_tokens": len(device_tokens),
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send push notification: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "push",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _format_title(self, event: AnomalyEvent) -> str:
        """Format notification title"""
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴",
        }.get(severity.lower(), "📊")
        
        return f"{severity_emoji} {event.instrument} - {anomaly_type.replace('_', ' ').title()}"
    
    def _format_body(self, event: AnomalyEvent) -> str:
        """Format notification body"""
        body_parts = [event.description]
        
        if event.price:
            body_parts.append(f"Price: ₹{event.price:,.2f}")
        
        if event.z_score:
            body_parts.append(f"Z-Score: {event.z_score:.2f}")
        
        return " | ".join(body_parts)
    
    async def send_test(self, user_id: str, device_tokens: list[str]) -> dict:
        """
        Send a test push notification
        
        Args:
            user_id: User ID
            device_tokens: List of FCM device tokens
            
        Returns:
            dict with status and details
        """
        if not FIREBASE_AVAILABLE or not self.initialized:
            return {
                "status": "skipped",
                "channel": "push",
                "reason": "Firebase not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not device_tokens:
            return {
                "status": "skipped",
                "channel": "push",
                "reason": "No device tokens registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title="🔔 Test Alert from Signalix",
                    body="This is a test push notification. Your alerts are working!",
                ),
                data={
                    "type": "test_alert",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                tokens=device_tokens,
            )
            
            response = messaging.send_multicast(message)
            
            return {
                "status": "sent",
                "channel": "push",
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "total_tokens": len(device_tokens),
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test push: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "push",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
