"""
Email Alert Channel
Sends email alerts via SendGrid

Requirements: 13.2, 13.6
"""
import logging
from typing import Optional
from datetime import datetime
import os
import httpx
from shared.database.models import AnomalyEvent

logger = logging.getLogger(__name__)


class EmailChannel:
    """
    Email alert delivery via SendGrid API.
    Sends formatted HTML email digest with AnomalyEvent details.
    """
    
    def __init__(self):
        """Initialize email channel"""
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("SENDGRID_FROM_EMAIL", "alerts@signalixai.com")
        self.from_name = os.getenv("SENDGRID_FROM_NAME", "Signalix Alerts")
        self.enabled = bool(self.api_key)
        
        if not self.enabled:
            logger.warning("SendGrid API key not configured, email alerts disabled")
    
    async def send(self, user_id: str, event: AnomalyEvent, rule_id: str, email_address: str) -> dict:
        """
        Send email alert
        
        Args:
            user_id: User ID
            event: AnomalyEvent instance
            rule_id: Alert rule ID
            email_address: User's email address
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "email",
                "reason": "SendGrid not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not email_address:
            return {
                "status": "skipped",
                "channel": "email",
                "reason": "No email address registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Format email
            subject = self._format_subject(event)
            html_content = self._format_html(event)
            text_content = self._format_text(event)
            
            # Prepare SendGrid API request
            url = "https://api.sendgrid.com/v3/mail/send"
            
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": email_address}],
                        "subject": subject,
                    }
                ],
                "from": {
                    "email": self.from_email,
                    "name": self.from_name,
                },
                "content": [
                    {
                        "type": "text/plain",
                        "value": text_content,
                    },
                    {
                        "type": "text/html",
                        "value": html_content,
                    }
                ],
                "categories": ["anomaly_alert"],
                "custom_args": {
                    "rule_id": rule_id,
                    "event_id": str(event.id),
                    "user_id": user_id,
                },
            }
            
            # Send via SendGrid API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                
                response.raise_for_status()
            
            logger.info(f"Sent email alert to {email_address}")
            
            return {
                "status": "sent",
                "channel": "email",
                "to": email_address,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"SendGrid API error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "failed",
                "channel": "email",
                "error": f"SendGrid API error: {e.response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "email",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def _format_subject(self, event: AnomalyEvent) -> str:
        """Format email subject"""
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        severity_prefix = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴",
        }.get(severity.lower(), "📊")
        
        return f"{severity_prefix} Signalix Alert: {event.instrument} - {anomaly_type.replace('_', ' ').title()}"
    
    def _format_html(self, event: AnomalyEvent) -> str:
        """Format HTML email content"""
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        # Severity color
        severity_color = {
            "low": "#3b82f6",
            "medium": "#f59e0b",
            "high": "#ef4444",
            "critical": "#dc2626",
        }.get(severity.lower(), "#6b7280")
        
        # Build HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">Signalix Alert</h1>
    </div>
    
    <div style="background: white; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 10px 10px;">
        
        <div style="background: {severity_color}; color: white; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <h2 style="margin: 0; font-size: 18px; text-transform: uppercase;">{severity} Alert</h2>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold; width: 40%;">Instrument</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{event.instrument}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Asset Class</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{event.asset_class.upper()}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Anomaly Type</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{anomaly_type.replace('_', ' ').title()}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Detected At</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{event.detected_at.strftime('%Y-%m-%d %H:%M:%S') if event.detected_at else 'N/A'}</td>
            </tr>
        </table>
        
        <div style="background: #f9fafb; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="margin-top: 0; color: #374151;">Description</h3>
            <p style="margin: 0; color: #6b7280;">{event.description}</p>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
"""
        
        # Add optional fields
        if event.price:
            html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold; width: 40%;">Price</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">₹{event.price:,.2f}</td>
            </tr>
"""
        
        if event.volume:
            html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Volume</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{event.volume:,.0f}</td>
            </tr>
"""
        
        if event.z_score:
            html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Z-Score</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{event.z_score:.2f}</td>
            </tr>
"""
        
        if event.affected_instruments:
            html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Affected Instruments</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{', '.join(event.affected_instruments)}</td>
            </tr>
"""
        
        html += """
        </table>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
            <p style="color: #6b7280; font-size: 14px; margin: 0;">
                This alert was sent by Signalix Alert Engine<br>
                <a href="https://signalixai.com" style="color: #667eea; text-decoration: none;">Visit Dashboard</a>
            </p>
        </div>
        
    </div>
    
</body>
</html>
"""
        
        return html
    
    def _format_text(self, event: AnomalyEvent) -> str:
        """Format plain text email content"""
        severity = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)
        anomaly_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        
        lines = [
            "SIGNALIX ALERT",
            "=" * 50,
            "",
            f"Severity: {severity.upper()}",
            f"Instrument: {event.instrument}",
            f"Asset Class: {event.asset_class.upper()}",
            f"Anomaly Type: {anomaly_type.replace('_', ' ').title()}",
            f"Detected At: {event.detected_at.strftime('%Y-%m-%d %H:%M:%S') if event.detected_at else 'N/A'}",
            "",
            "Description:",
            event.description,
            "",
        ]
        
        if event.price:
            lines.append(f"Price: ₹{event.price:,.2f}")
        
        if event.volume:
            lines.append(f"Volume: {event.volume:,.0f}")
        
        if event.z_score:
            lines.append(f"Z-Score: {event.z_score:.2f}")
        
        if event.affected_instruments:
            lines.append(f"Affected Instruments: {', '.join(event.affected_instruments)}")
        
        lines.extend([
            "",
            "=" * 50,
            "This alert was sent by Signalix Alert Engine",
            "Visit: https://signalixai.com",
        ])
        
        return "\n".join(lines)
    
    async def send_test(self, user_id: str, email_address: str) -> dict:
        """
        Send a test email
        
        Args:
            user_id: User ID
            email_address: User's email address
            
        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {
                "status": "skipped",
                "channel": "email",
                "reason": "SendGrid not configured",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        if not email_address:
            return {
                "status": "skipped",
                "channel": "email",
                "reason": "No email address registered",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            subject = "🔔 Test Alert from Signalix"
            
            html_content = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2>Test Alert from Signalix</h2>
    <p>This is a test email to verify your alert delivery is working correctly.</p>
    <p>Your email alerts are configured and operational!</p>
    <p style="color: #666; font-size: 14px; margin-top: 30px;">
        Sent at: """ + datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC') + """
    </p>
</body>
</html>
"""
            
            text_content = f"Test Alert from Signalix\n\nThis is a test email. Your alerts are working!\n\nSent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            url = "https://api.sendgrid.com/v3/mail/send"
            
            payload = {
                "personalizations": [{"to": [{"email": email_address}], "subject": subject}],
                "from": {"email": self.from_email, "name": self.from_name},
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_content}
                ],
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                
                response.raise_for_status()
            
            return {
                "status": "sent",
                "channel": "email",
                "to": email_address,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Failed to send test email: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": "email",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
