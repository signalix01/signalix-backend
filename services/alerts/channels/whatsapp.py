"""
WhatsApp Alert Channel
Sends alerts via Twilio WhatsApp API

Requirements: 13.2, 13.6
"""
import logging
from typing import Optional
from datetime import datetime
import os
import httpx
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)


class WhatsAppChannel:
    """
    WhatsApp alert delivery via Twilio WhatsApp API.
    Sends formatted template messages with AnomalyEvent details.
    """
    
    def __init__(self):
        """Initialize WhatsApp channel"""
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")  # Twilio sandbox default
        self.enabled = bool(self.account_sid and self.auth_token)
        
        if not self.enabled:
            logger.warning("Twilio credentials not configured, WhatsApp alerts disabled")
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str, phone_number: str) -> dict:
        """
        Send WhatsApp alert
        
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
                "channel": "whatsapp",
                "reason": "Twilio not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not phone_number:
            return {
                "status": "skipped",
                "channel": "whatsapp",
                "reason": "No phone number registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Format message
            message_body = self._format_message(event)
            
            # Prepare Twilio API request
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            
            # Ensure phone number has whatsapp: prefix
            to_number = phone_number if phone_number.startswith("whatsapp:") else f"whatsapp:{phone_number}"
            
            data = {
                "From": self.from_number,
                "To": to_number,
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
            
            logger.info(f"Sent WhatsApp alert to {to_number}, SID: {result.get('sid')}")
            
            return {
                "status": "sent",
                "channel": "whatsapp",
                "message_sid": result.get("sid"),
                "to": to_number,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Twilio API error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "failed",
                "channel": "whatsapp",
                "error": f"Twilio API error: {e.response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "whatsapp",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _format_message(self, event: AnomalyEvent) -> str:
        """
        Format WhatsApp message with AnomalyEvent details
        
        Args:
            event: AnomalyEvent instance
            
        Returns:
            Formatted message string
        """
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        # Severity emoji
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴",
        }.get(severity.lower(), "📊")
        
        # Build message
        lines = [
            f"{severity_emoji} *Signalix Alert*",
            "",
            f"*Instrument:* {event.instrument}",
            f"*Type:* {anomaly_type.replace('_', ' ').title()}",
            f"*Severity:* {severity.upper()}",
            "",
            f"*Description:*",
            event.description,
        ]
        
        # Add optional fields
        if event.price:
            lines.append(f"\n*Price:* ₹{event.price:,.2f}")
        
        if event.volume:
            lines.append(f"*Volume:* {event.volume:,.0f}")
        
        if event.z_score:
            lines.append(f"*Z-Score:* {event.z_score:.2f}")
        
        if event.affected_instruments:
            lines.append(f"\n*Affected:* {', '.join(event.affected_instruments[:3])}")
        
        # Add timestamp
        detected_time = event.detected_at.strftime("%H:%M:%S") if event.detected_at else "N/A"
        lines.append(f"\n⏰ Detected at {detected_time}")
        
        return "\n".join(lines)
    
    async def send_test(self, user_id: str, phone_number: str) -> dict:
        """
        Send a test WhatsApp message
        
        Args:
            user_id: User ID
            phone_number: User's phone number
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "whatsapp",
                "reason": "Twilio not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not phone_number:
            return {
                "status": "skipped",
                "channel": "whatsapp",
                "reason": "No phone number registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            message_body = (
                "🔔 *Test Alert from Signalix*\n\n"
                "This is a test WhatsApp message.\n"
                "Your alerts are working correctly!\n\n"
                f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            to_number = phone_number if phone_number.startswith("whatsapp:") else f"whatsapp:{phone_number}"
            
            data = {
                "From": self.from_number,
                "To": to_number,
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
                "channel": "whatsapp",
                "message_sid": result.get("sid"),
                "to": to_number,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test WhatsApp: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "whatsapp",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
