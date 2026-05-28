"""
SMS Alert Channel
Sends SMS alerts via Twilio (critical alerts only)

Requirements: 13.2, 13.6
"""
import logging
from typing import Optional
from datetime import datetime
import os
import httpx
from shared.database.models import AnomalyEvent, AnomalySeverity

logger = logging.getLogger(__name__)


class SMSChannel:
    """
    SMS alert delivery via Twilio SMS API.
    Only sends CRITICAL severity alerts to avoid SMS costs.
    """
    
    def __init__(self):
        """Initialize SMS channel"""
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER")
        self.enabled = bool(self.account_sid and self.auth_token and self.from_number)
        
        if not self.enabled:
            logger.warning("Twilio credentials not configured, SMS alerts disabled")
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str, phone_number: str) -> dict:
        """
        Send SMS alert (critical alerts only)
        
        Args:
            user_id: User ID
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            phone_number: User's phone number (E.164 format)
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "sms",
                "reason": "Twilio not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not phone_number:
            return {
                "status": "skipped",
                "channel": "sms",
                "reason": "No phone number registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        # Only send SMS for CRITICAL severity alerts
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        if severity.lower() != "critical":
            return {
                "status": "skipped",
                "channel": "sms",
                "reason": "SMS only for critical alerts",
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Format message (SMS has 160 char limit, keep it concise)
            message_body = self._format_message(event)
            
            # Prepare Twilio API request
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            
            data = {
                "From": self.from_number,
                "To": phone_number,
                "Body": message_body,
            }
            
            # Send via Twilio API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                    timeout=30.0,
                )
                
                response.raise_for_status()
                result = response.json()
            
            logger.info(f"Sent SMS alert to {phone_number}, SID: {result.get('sid')}")
            
            return {
                "status": "sent",
                "channel": "sms",
                "message_sid": result.get("sid"),
                "to": phone_number,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Twilio API error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "failed",
                "channel": "sms",
                "error": f"Twilio API error: {e.response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "sms",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _format_message(self, event: AnomalyEvent) -> str:
        """
        Format SMS message (keep under 160 chars)
        
        Args:
            event: AnomalyEvent instance
            
        Returns:
            Formatted message string
        """
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        # Build concise message
        message = f"🔴 CRITICAL: {event.instrument} - {anomaly_type.replace('_', ' ').title()}"
        
        # Add price if available
        if event.price:
            message += f" @ ₹{event.price:,.0f}"
        
        # Add brief description (truncate if needed)
        desc = event.description[:60] + "..." if len(event.description) > 60 else event.description
        message += f". {desc}"
        
        # Ensure under 160 chars
        if len(message) > 160:
            message = message[:157] + "..."
        
        return message
    
    async def send_test(self, user_id: str, phone_number: str) -> dict:
        """
        Send a test SMS message
        
        Args:
            user_id: User ID
            phone_number: User's phone number
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "sms",
                "reason": "Twilio not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not phone_number:
            return {
                "status": "skipped",
                "channel": "sms",
                "reason": "No phone number registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            message_body = f"🔔 Test SMS from Signalix. Your critical alerts are working! {datetime.utcnow().strftime('%H:%M')}"
            
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            
            data = {
                "From": self.from_number,
                "To": phone_number,
                "Body": message_body,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                    timeout=30.0,
                )
                
                response.raise_for_status()
                result = response.json()
            
            return {
                "status": "sent",
                "channel": "sms",
                "message_sid": result.get("sid"),
                "to": phone_number,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test SMS: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "sms",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
