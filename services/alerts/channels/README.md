# Alert Delivery Channels

This directory implements all 7 delivery channels for the Signalix Alert Engine.

## Overview

Each channel is responsible for delivering anomaly alerts to users through different communication methods. All channels follow a consistent interface and include comprehensive error handling, retry logic, and test methods.

## Channels

### 1. In-App Channel (`in_app.py`)

**Purpose:** Real-time alerts via WebSocket  
**Technology:** Redis Pub/Sub  
**Requirements:** 13.2, 13.6

**Features:**
- Publishes to Redis channel `user_alerts:{user_id}`
- WebSocket clients subscribe to receive real-time alerts
- Offline queueing: stores up to 100 alerts when user is offline
- Automatic delivery on reconnection
- 7-day queue expiry

**Usage:**
```python
from services.alerts.channels import InAppChannel

channel = InAppChannel(redis_client)
result = await channel.send(user_id, event, rule_id)
```

**Payload Format:**
```json
{
  "type": "anomaly_alert",
  "rule_id": "...",
  "event_id": "...",
  "instrument": "BANKNIFTY",
  "anomaly_type": "flash_crash",
  "severity": "critical",
  "description": "...",
  "detected_at": "2024-01-15T10:30:00",
  "price": 45250.50,
  "volume": 125000,
  "z_score": -4.2,
  "affected_instruments": ["NIFTY", "FINNIFTY"]
}
```

---

### 2. Push Notification Channel (`push.py`)

**Purpose:** Mobile push notifications  
**Technology:** Firebase Cloud Messaging (FCM)  
**Requirements:** 13.2, 13.6

**Features:**
- Sends to all registered device tokens
- Platform-specific configuration (Android/iOS)
- Rich notifications with custom data payload
- Automatic badge management
- Sound and priority settings

**Configuration:**
```env
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/service-account.json
```

**Usage:**
```python
from services.alerts.channels import PushChannel

channel = PushChannel()
result = await channel.send(user_id, event, rule_id, device_tokens)
```

**Notification Format:**
- **Title:** `🚨 BANKNIFTY - Flash Crash`
- **Body:** `Flash crash detected: 5% drop in 3 minutes | Price: ₹45,250.50 | Z-Score: -4.2`
- **Data:** Full event details for in-app handling

---

### 3. WhatsApp Channel (`whatsapp.py`)

**Purpose:** WhatsApp messages  
**Technology:** Twilio WhatsApp API  
**Requirements:** 13.2, 13.6

**Features:**
- Formatted template messages
- Emoji indicators for severity
- Markdown-style formatting
- Automatic phone number formatting (E.164)

**Configuration:**
```env
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

**Usage:**
```python
from services.alerts.channels import WhatsAppChannel

channel = WhatsAppChannel()
result = await channel.send(user_id, event, rule_id, phone_number)
```

**Message Format:**
```
🔴 *Signalix Alert*

*Instrument:* BANKNIFTY
*Type:* Flash Crash
*Severity:* CRITICAL

*Description:*
Flash crash detected: 5% drop in 3 minutes

*Price:* ₹45,250.50
*Volume:* 125,000
*Z-Score:* -4.2

*Affected:* NIFTY, FINNIFTY

⏰ Detected at 10:30:00
```

---

### 4. SMS Channel (`sms.py`)

**Purpose:** SMS alerts (critical only)  
**Technology:** Twilio SMS API  
**Requirements:** 13.2, 13.6

**Features:**
- **Critical alerts only** (cost control)
- Concise messages (160 char limit)
- Automatic truncation
- E.164 phone number format

**Configuration:**
```env
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+14155551234
```

**Usage:**
```python
from services.alerts.channels import SMSChannel

channel = SMSChannel()
result = await channel.send(user_id, event, rule_id, phone_number)
```

**Message Format:**
```
🔴 CRITICAL: BANKNIFTY - Flash Crash @ ₹45,250. Flash crash detected: 5% drop in 3 minutes...
```

---

### 5. Email Channel (`email.py`)

**Purpose:** Email alerts with HTML digest  
**Technology:** SendGrid API  
**Requirements:** 13.2, 13.6

**Features:**
- Beautiful HTML email templates
- Plain text fallback
- Responsive design
- Severity color coding
- Detailed event information table

**Configuration:**
```env
SENDGRID_API_KEY=SG.xxx
SENDGRID_FROM_EMAIL=alerts@signalix.com
SENDGRID_FROM_NAME=Signalix Alerts
```

**Usage:**
```python
from services.alerts.channels import EmailChannel

channel = EmailChannel()
result = await channel.send(user_id, event, rule_id, email_address)
```

**Email Features:**
- Gradient header with branding
- Color-coded severity badge
- Structured data table
- Responsive HTML design
- Plain text alternative

---

### 6. Telegram Channel (`telegram.py`)

**Purpose:** Telegram bot messages  
**Technology:** Telegram Bot API  
**Requirements:** 13.2, 13.6

**Features:**
- Markdown-formatted messages
- Emoji indicators
- Inline code formatting for symbols
- Rich text support

**Configuration:**
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
```

**Setup:**
1. Create bot via [@BotFather](https://t.me/botfather)
2. Get bot token
3. Users start chat with bot to get chat_id

**Usage:**
```python
from services.alerts.channels import TelegramChannel

channel = TelegramChannel()
result = await channel.send(user_id, event, rule_id, chat_id)
```

**Message Format:**
```
🔴 *SIGNALIX ALERT*

*Instrument:* `BANKNIFTY`
*Type:* Flash Crash
*Severity:* CRITICAL
*Asset Class:* FO

*Description:*
Flash crash detected: 5% drop in 3 minutes

💰 *Price:* ₹45,250.50
📊 *Volume:* 125,000
📈 *Z-Score:* -4.2

🔗 *Affected:* `NIFTY`, `FINNIFTY`

⏰ *Detected:* 2024-01-15 10:30:00
```

---

### 7. Webhook Channel (`webhook.py`)

**Purpose:** Custom webhook integration  
**Technology:** HTTP POST with HMAC signature  
**Requirements:** 13.2, 13.6, 13.7

**Features:**
- Full event JSON payload
- HMAC-SHA256 signature for authenticity
- Custom headers for metadata
- 30-second timeout
- Comprehensive error handling

**Configuration:**
- Configured per alert rule (no global config)
- Users provide webhook URL and secret

**Usage:**
```python
from services.alerts.channels import WebhookChannel

channel = WebhookChannel()
result = await channel.send(
    user_id, 
    event, 
    rule_id, 
    webhook_url,
    webhook_secret
)
```

**Request Format:**
```http
POST /webhook HTTP/1.1
Host: example.com
Content-Type: application/json
User-Agent: Signalix-Alert-Engine/1.0
X-Signalix-Event: anomaly_alert
X-Signalix-Rule-ID: 550e8400-e29b-41d4-a716-446655440000
X-Signalix-Timestamp: 2024-01-15T10:30:00Z
X-Signalix-Signature: sha256=abc123...

{
  "event_type": "anomaly_alert",
  "rule_id": "...",
  "user_id": "...",
  "event": {
    "id": "...",
    "instrument": "BANKNIFTY",
    "asset_class": "fo",
    "anomaly_type": "flash_crash",
    "severity": "critical",
    "detected_at": "2024-01-15T10:30:00",
    "description": "...",
    "z_score": -4.2,
    "price": 45250.50,
    "volume": 125000,
    "affected_instruments": ["NIFTY", "FINNIFTY"],
    "raw_data": {...}
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Signature Verification:**
```python
import hmac
import hashlib

def verify_webhook(payload: str, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)
```

---

## Common Interface

All channels implement the same interface:

```python
class Channel:
    async def send(
        self, 
        user_id: str, 
        event: AnomalyEvent, 
        rule_id: str,
        *channel_specific_args
    ) -> dict:
        """
        Send alert via this channel
        
        Returns:
            {
                "status": "sent" | "failed" | "skipped",
                "channel": "channel_name",
                "timestamp": "ISO timestamp",
                # ... channel-specific fields
            }
        """
        pass
    
    async def send_test(
        self,
        user_id: str,
        *channel_specific_args
    ) -> dict:
        """Send a test alert"""
        pass
```

---

## Response Format

All channels return a standardized response:

**Success:**
```json
{
  "status": "sent",
  "channel": "whatsapp",
  "message_sid": "SM123",
  "to": "whatsapp:+919876543210",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Failure:**
```json
{
  "status": "failed",
  "channel": "email",
  "error": "SendGrid API error: 401",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Skipped:**
```json
{
  "status": "skipped",
  "channel": "sms",
  "reason": "SMS only for critical alerts",
  "severity": "medium",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Error Handling

All channels implement:

1. **Graceful degradation:** If a channel is not configured, it returns `status: "skipped"`
2. **Timeout handling:** 30-second timeout for all external API calls
3. **Retry logic:** Handled by the delivery engine (not individual channels)
4. **Detailed error logging:** All errors logged with full context
5. **Status tracking:** Every delivery attempt logged to `alert_delivery_log`

---

## Testing

Run all channel tests:

```bash
pytest services/alerts/channels/test_channels.py -v
```

Test individual channel:

```bash
pytest services/alerts/channels/test_channels.py::test_in_app_channel_send_success -v
```

All tests use mocked external APIs (no real API calls).

---

## Configuration Summary

| Channel   | Required Env Vars                                      | Optional |
|-----------|-------------------------------------------------------|----------|
| In-App    | `REDIS_URL`                                           | -        |
| Push      | `FIREBASE_SERVICE_ACCOUNT_PATH`                       | -        |
| WhatsApp  | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`             | `TWILIO_WHATSAPP_NUMBER` |
| SMS       | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | - |
| Email     | `SENDGRID_API_KEY`                                    | `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME` |
| Telegram  | `TELEGRAM_BOT_TOKEN`                                  | -        |
| Webhook   | (per-rule configuration)                              | -        |

---

## Performance

| Channel   | Typical Latency | Cost per Alert | Rate Limits |
|-----------|----------------|----------------|-------------|
| In-App    | < 100ms        | Free           | Unlimited   |
| Push      | < 500ms        | Free           | FCM limits  |
| WhatsApp  | 1-3s           | $0.005         | Twilio limits |
| SMS       | 1-3s           | $0.01          | Twilio limits |
| Email     | 1-2s           | $0.0001        | SendGrid limits |
| Telegram  | 500ms-1s       | Free           | 30 msg/sec  |
| Webhook   | Variable       | Free           | User's server |

---

## Security

1. **API Keys:** All stored in environment variables, never in code
2. **HMAC Signatures:** Webhook requests signed with HMAC-SHA256
3. **TLS:** All external API calls use HTTPS
4. **Rate Limiting:** Enforced at delivery engine level
5. **Input Validation:** All user inputs validated before sending

---

## Future Enhancements

- [ ] Slack integration
- [ ] Discord integration
- [ ] Microsoft Teams integration
- [ ] Voice call alerts (Twilio Voice)
- [ ] Custom SMTP email support
- [ ] Batch delivery optimization
- [ ] Delivery analytics dashboard

---

## Support

For issues or questions:
- Check logs: `services/alerts/channels/*.log`
- Review test failures: `pytest services/alerts/channels/test_channels.py -v`
- Verify configuration: All required env vars set
- Test individual channels: Use `send_test()` methods

---

**Last Updated:** 2024-01-15  
**Requirements:** 13.2, 13.6, 13.7  
**Task:** Phase 9, Task 40
