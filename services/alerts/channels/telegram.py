"""
Telegram Alert Channel
Sends alerts via Telegram Bot API

Requirements: 13.2, 13.6
"""
import logging
from typing import Optional
from datetime import datetime
import os
import httpx
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)


class TelegramChannel:
    """
    Telegram alert delivery via Telegram Bot API.
    Sends Markdown-formatted alerts to user's Telegram chat.
    """
    
    def __init__(self):
        """Initialize Telegram channel"""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.enabled = bool(self.bot_token)
        
        if not self.enabled:
            logger.warning("Telegram bot token not configured, Telegram alerts disabled")
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str, chat_id: str) -> dict:
        """
        Send Telegram alert
        
        Args:
            user_id: User ID
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            chat_id: User's Telegram chat ID
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "telegram",
                "reason": "Telegram bot not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not chat_id:
            return {
                "status": "skipped",
                "channel": "telegram",
                "reason": "No Telegram chat ID registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Format message in Markdown
            message_text = self._format_message(event)
            
            # Prepare Telegram API request
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            
            # Send via Telegram API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=30.0,
                )
                
                response.raise_for_status()
                result = response.json()
            
            if not result.get("ok"):
                raise Exception(f"Telegram API error: {result.get('description')}")
            
            logger.info(f"Sent Telegram alert to chat {chat_id}, message_id: {result['result']['message_id']}")
            
            return {
                "status": "sent",
                "channel": "telegram",
                "chat_id": chat_id,
                "message_id": result["result"]["message_id"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram API error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "failed",
                "channel": "telegram",
                "error": f"Telegram API error: {e.response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "telegram",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _format_message(self, event: AnomalyEvent) -> str:
        """
        Format Telegram message with Markdown formatting
        
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
        
        # Build message with Markdown formatting
        lines = [
            f"{severity_emoji} *SIGNALIX ALERT*",
            "",
            f"*Instrument:* `{event.instrument}`",
            f"*Type:* {anomaly_type.replace('_', ' ').title()}",
            f"*Severity:* {severity.upper()}",
            f"*Asset Class:* {event.asset_class.upper()}",
            "",
            f"*Description:*",
            event.description,
        ]
        
        # Add optional fields
        if event.price:
            lines.append(f"\n💰 *Price:* ₹{event.price:,.2f}")
        
        if event.volume:
            lines.append(f"📊 *Volume:* {event.volume:,.0f}")
        
        if event.z_score:
            lines.append(f"📈 *Z-Score:* {event.z_score:.2f}")
        
        if event.affected_instruments:
            affected = ", ".join([f"`{inst}`" for inst in event.affected_instruments[:5]])
            lines.append(f"\n🔗 *Affected:* {affected}")
        
        # Add timestamp
        detected_time = event.detected_at.strftime("%Y-%m-%d %H:%M:%S") if event.detected_at else "N/A"
        lines.append(f"\n⏰ *Detected:* {detected_time}")
        
        return "\n".join(lines)
    
    async def send_test(self, user_id: str, chat_id: str) -> dict:
        """
        Send a test Telegram message
        
        Args:
            user_id: User ID
            chat_id: User's Telegram chat ID
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "telegram",
                "reason": "Telegram bot not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not chat_id:
            return {
                "status": "skipped",
                "channel": "telegram",
                "reason": "No Telegram chat ID registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            message_text = (
                "🔔 *Test Alert from Signalix*\n\n"
                "This is a test message to verify your Telegram alerts are working correctly.\n\n"
                "✅ Your alerts are configured and operational!\n\n"
                f"⏰ *Sent:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "Markdown",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=30.0,
                )
                
                response.raise_for_status()
                result = response.json()
            
            if not result.get("ok"):
                raise Exception(f"Telegram API error: {result.get('description')}")
            
            return {
                "status": "sent",
                "channel": "telegram",
                "chat_id": chat_id,
                "message_id": result["result"]["message_id"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test Telegram: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "telegram",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
