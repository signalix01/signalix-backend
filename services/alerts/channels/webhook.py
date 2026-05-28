"""
Webhook Alert Channel
Sends alerts to custom webhook URLs with HMAC signature

Requirements: 13.2, 13.6, 13.7
"""
import logging
import hmac
import hashlib
import json
from typing import Optional
from datetime import datetime
import httpx
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)


class WebhookChannel:
    """
    Webhook alert delivery to custom URLs.
    Sends full AnomalyEvent JSON with HMAC-SHA256 signature for authenticity.
    """
    
    def __init__(self):
        """Initialize webhook channel"""
        pass
    
    async def send(
        self, 
        user_id: str, 
        event: AnomalyEvent, 
        rule_id: str, 
        webhook_url: str,
        webhook_secret: Optional[str] = None
    ) -> dict:
        """
        Send webhook alert
        
        Args:
            user_id: User ID
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            webhook_url: Target webhook URL
            webhook_secret: Secret for HMAC signature (optional)
            
        Returns:
            dict with status and details
        """
        if not webhook_url:
            return {
                "status": "skipped",
                "channel": "webhook",
                "reason": "No webhook URL configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Build payload
            payload = self._build_payload(event, rule_id, user_id)
            payload_json = json.dumps(payload, default=str)
            
            # Generate HMAC signature
            signature = self._generate_signature(payload_json, webhook_secret) if webhook_secret else None
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Signalix-Alert-Engine/1.0",
                "X-Signalix-Event": "anomaly_alert",
                "X-Signalix-Rule-ID": rule_id,
                "X-Signalix-Timestamp": datetime.utcnow().isoformat(),
            }
            
            if signature:
                headers["X-Signalix-Signature"] = signature
            
            # Send webhook
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                
                response.raise_for_status()
            
            logger.info(f"Sent webhook alert to {webhook_url}, status: {response.status_code}")
            
            return {
                "status": "sent",
                "channel": "webhook",
                "url": webhook_url,
                "response_status": response.status_code,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook HTTP error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "failed",
                "channel": "webhook",
                "url": webhook_url,
                "error": f"HTTP {e.response.status_code}",
                "response_body": e.response.text[:200],
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.TimeoutException:
            logger.error(f"Webhook timeout: {webhook_url}")
            return {
                "status": "failed",
                "channel": "webhook",
                "url": webhook_url,
                "error": "Request timeout",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "webhook",
                "url": webhook_url,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _build_payload(self, event: AnomalyEvent, rule_id: str, user_id: str) -> dict:
        """
        Build webhook payload with full event details
        
        Args:
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            user_id: User ID
            
        Returns:
            dict payload
        """
        return {
            "event_type": "anomaly_alert",
            "rule_id": rule_id,
            "user_id": user_id,
            "event": {
                "id": str(event.id),
                "instrument": event.instrument,
                "asset_class": event.asset_class,
                "exchange": event.exchange,
                "anomaly_type": event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type),
                "severity": event.severity.value if hasattr(event.severity, 'value') else str(event.severity),
                "detected_at": event.detected_at.isoformat() if event.detected_at else None,
                "description": event.description,
                "z_score": event.z_score,
                "price": event.price,
                "volume": event.volume,
                "affected_instruments": event.affected_instruments or [],
                "raw_data": event.raw_data,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def _generate_signature(self, payload: str, secret: str) -> str:
        """
        Generate HMAC-SHA256 signature for webhook authenticity
        
        Args:
            payload: JSON payload string
            secret: Webhook secret
            
        Returns:
            Hex-encoded HMAC signature
        """
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def verify_signature(self, payload: str, signature: str, secret: str) -> bool:
        """
        Verify webhook signature (for webhook receivers)
        
        Args:
            payload: JSON payload string
            signature: Received signature (format: "sha256=...")
            secret: Webhook secret
            
        Returns:
            True if signature is valid
        """
        if not signature or not signature.startswith("sha256="):
            return False
        
        expected_signature = self._generate_signature(payload, secret)
        
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature)
    
    async def send_test(self, user_id: str, webhook_url: str, webhook_secret: Optional[str] = None) -> dict:
        """
        Send a test webhook
        
        Args:
            user_id: User ID
            webhook_url: Target webhook URL
            webhook_secret: Secret for HMAC signature (optional)
            
        Returns:
            dict with status and details
        """
        if not webhook_url:
            return {
                "status": "skipped",
                "channel": "webhook",
                "reason": "No webhook URL configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            payload = {
                "event_type": "test_alert",
                "user_id": user_id,
                "message": "This is a test webhook from Signalix",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            payload_json = json.dumps(payload)
            signature = self._generate_signature(payload_json, webhook_secret) if webhook_secret else None
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Signalix-Alert-Engine/1.0",
                "X-Signalix-Event": "test_alert",
                "X-Signalix-Timestamp": datetime.utcnow().isoformat(),
            }
            
            if signature:
                headers["X-Signalix-Signature"] = signature
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                
                response.raise_for_status()
            
            return {
                "status": "sent",
                "channel": "webhook",
                "url": webhook_url,
                "response_status": response.status_code,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test webhook: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "webhook",
                "url": webhook_url,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
