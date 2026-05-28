# Alert Delivery Engine

## Overview

The `AlertDeliveryEngine` orchestrates alert delivery across all 7 delivery channels with retry logic, offline queueing, and comprehensive logging.

**Requirements:** 13.2, 14.1, 14.2, 14.3, 14.4

## Features

### 1. Multi-Channel Delivery

Supports all 7 delivery channels:
- **in_app**: WebSocket pub/sub via Redis
- **push**: Firebase Cloud Messaging (FCM)
- **email**: SendGrid API
- **sms**: Twilio SMS (critical alerts only)
- **whatsapp**: Twilio WhatsApp API
- **telegram**: Telegram Bot API
- **webhook**: Custom webhook URLs with HMAC signatures

### 2. Concurrent vs Sequential Delivery

**CRITICAL Alerts** (severity = CRITICAL):
- Delivers to all channels **concurrently** using `asyncio.gather()`
- Ensures fastest possible delivery for urgent alerts
- All channels receive the alert simultaneously

**Non-Critical Alerts** (severity = LOW, MEDIUM, HIGH):
- Delivers to channels **sequentially**
- Avoids overwhelming external APIs with concurrent requests
- Respects rate limits

### 3. Retry Logic

- **3 retries** with exponential backoff
- Retry delays: **30s, 2min, 10min**
- Each retry attempt is logged separately
- After 3 failed attempts, marks delivery as permanently failed

### 4. Offline Queue

For the `in_app` channel:
- If user is offline (0 WebSocket subscribers), alerts are queued in Redis
- Queue key: `offline_alerts:{user_id}`
- Max 100 alerts per user (FIFO)
- 7-day expiry
- Delivered when user reconnects

### 5. Delivery Logging

Every delivery attempt is logged to `alert_delivery_log` table:
- `anomaly_event_id`: Event that triggered the alert
- `alert_rule_id`: Rule that matched
- `user_id`: Recipient user
- `channel`: Delivery channel
- `status`: pending, sent, failed, skipped
- `attempt_number`: 1, 2, or 3
- `delivered_at`: Timestamp of successful delivery
- `error_message`: Error details if failed
- `detection_to_delivery_ms`: Latency tracking

### 6. Latency Tracking

Tracks end-to-end latency from anomaly detection to delivery:
- Calculated as: `datetime.utcnow() - event.detected_at`
- Stored in milliseconds
- Target: p95 < 5 seconds for critical alerts

## Usage

### Basic Usage

```python
from services.alerts.delivery_engine import AlertDeliveryEngine
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

# Initialize
db_session = AsyncSession(...)
redis_client = redis.from_url("redis://localhost:6379")

engine = AlertDeliveryEngine(db_session, redis_client)

# Deliver alert
result = await engine.deliver(
    event=anomaly_event,
    matching_rules=[rule1, rule2]
)

print(result)
# {
#     "event_id": "...",
#     "rules_matched": 2,
#     "deliveries_attempted": 4,
#     "deliveries_successful": 3,
#     "deliveries_failed": 1,
#     "is_critical": False,
#     "timestamp": "2024-01-15T10:30:00Z"
# }
```

### Integration with Alert Matcher

```python
from services.alerts.matcher import AlertMatcher
from services.alerts.delivery_engine import AlertDeliveryEngine

# Match rules
matcher = AlertMatcher(db_session)
matching_rules = await matcher.match(event)

# Deliver
engine = AlertDeliveryEngine(db_session, redis_client)
result = await engine.deliver(event, matching_rules)
```

## Architecture

```
AlertDeliveryEngine
├── deliver(event, matching_rules)
│   ├── For each rule:
│   │   ├── Get user delivery preferences
│   │   ├── Create delivery tasks for each channel
│   │   └── Execute tasks (concurrent or sequential)
│   └── Return summary
│
├── _deliver_to_channel(channel, user_id, event, rule, is_critical)
│   ├── Retry loop (max 3 attempts)
│   │   ├── Log attempt
│   │   ├── Send to channel
│   │   ├── If success: log and return
│   │   ├── If failed: wait and retry
│   │   └── If skipped: log and return
│   └── Return result
│
├── _send_to_channel(channel, user_id, event, rule)
│   ├── Route to appropriate channel handler
│   ├── Get user preferences (email, phone, etc.)
│   └── Call channel.send()
│
└── _log_delivery_attempt(...)
    └── Insert into alert_delivery_log table
```

## Channel-Specific Behavior

### in_app (WebSocket)
- Publishes to Redis pub/sub channel: `user_alerts:{user_id}`
- If 0 subscribers, queues in `offline_alerts:{user_id}`
- Returns: `{"status": "sent", "subscribers": N, "queued_offline": bool}`

### push (FCM)
- Requires user's FCM device tokens
- Sends to all registered devices
- Returns: `{"status": "sent", "success_count": N, "failure_count": M}`

### email (SendGrid)
- Requires user's email address
- Sends HTML + plain text versions
- Returns: `{"status": "sent", "to": "user@example.com"}`

### sms (Twilio)
- **Only sends for CRITICAL severity alerts**
- Requires user's phone number (E.164 format)
- Message limited to 160 characters
- Returns: `{"status": "sent", "message_sid": "..."}`

### whatsapp (Twilio)
- Requires user's phone number (E.164 format)
- Sends formatted message with emoji
- Returns: `{"status": "sent", "message_sid": "..."}`

### telegram (Telegram Bot)
- Requires user's Telegram chat ID
- Sends Markdown-formatted message
- Returns: `{"status": "sent", "message_id": N}`

### webhook (Custom)
- Uses webhook URL from alert rule
- Sends full event JSON with HMAC signature
- Returns: `{"status": "sent", "response_status": 200}`

## User Preferences

The engine requires user preferences for delivery:
- Device tokens (push)
- Email address (email)
- Phone number (sms, whatsapp)
- Telegram chat ID (telegram)

**Current Implementation:**
- Placeholder methods return `None` or empty lists
- Channels are skipped if preferences not configured
- **TODO:** Implement user preferences service

## Testing

### Integration Tests

Run full integration tests (requires PostgreSQL + Redis):

```bash
pytest services/alerts/test_delivery_engine.py -v
```

Tests cover:
1. ✅ Deliver to all channels and verify logging
2. ✅ Retry on first failure
3. ✅ Concurrent delivery for CRITICAL alerts
4. ✅ Sequential delivery for non-critical alerts
5. ✅ Offline queue for in-app channel
6. ✅ Max retries exhausted
7. ✅ Latency tracking

### Unit Tests

Run unit tests with mocked dependencies:

```bash
pytest services/alerts/test_delivery_engine_unit.py -v
```

## Configuration

### Environment Variables

```bash
# Redis
REDIS_URL=redis://localhost:6379

# SendGrid (email)
SENDGRID_API_KEY=SG.xxx
SENDGRID_FROM_EMAIL=alerts@signalix.com
SENDGRID_FROM_NAME=Signalix Alerts

# Twilio (SMS + WhatsApp)
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_WHATSAPP_NUMBER=whatsapp:+1234567890

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABCxxx

# Firebase (Push)
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/firebase-credentials.json
```

### Retry Configuration

Modify retry delays in `AlertDeliveryEngine.__init__()`:

```python
self.retry_delays = [30, 120, 600]  # 30s, 2min, 10min
self.max_retries = 3
```

## Performance

### Latency Targets

- **CRITICAL alerts**: p95 < 5 seconds (detection to delivery)
- **Non-critical alerts**: p95 < 30 seconds

### Throughput

- Concurrent delivery: ~100ms per alert (all channels)
- Sequential delivery: ~500ms per alert (2 channels)

### Database Load

- 1 insert per delivery attempt
- Average: 2-3 inserts per alert (initial + retries)
- Index on `(user_id, created_at)` for efficient queries

## Monitoring

### Key Metrics

1. **Delivery Success Rate**: `sent / (sent + failed)`
2. **Average Latency**: `AVG(detection_to_delivery_ms)`
3. **Retry Rate**: `COUNT(attempt_number > 1) / COUNT(*)`
4. **Channel Availability**: `COUNT(status='sent') per channel`

### Queries

```sql
-- Delivery success rate (last 24h)
SELECT 
    channel,
    COUNT(*) FILTER (WHERE status = 'sent') * 100.0 / COUNT(*) as success_rate
FROM alert_delivery_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY channel;

-- Average latency by severity (last 24h)
SELECT 
    ae.severity,
    AVG(adl.detection_to_delivery_ms) as avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY adl.detection_to_delivery_ms) as p95_latency_ms
FROM alert_delivery_log adl
JOIN anomaly_events ae ON ae.id = adl.anomaly_event_id
WHERE adl.created_at > NOW() - INTERVAL '24 hours'
  AND adl.status = 'sent'
GROUP BY ae.severity;

-- Retry rate by channel (last 24h)
SELECT 
    channel,
    COUNT(*) FILTER (WHERE attempt_number > 1) * 100.0 / COUNT(*) as retry_rate
FROM alert_delivery_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY channel;
```

## Future Enhancements

1. **Rate Limiting**: Per-user, per-channel rate limits
2. **Quiet Hours**: Suppress non-critical alerts during configured hours
3. **Delivery Preferences**: User-configurable channel priorities
4. **Batch Delivery**: Group multiple alerts into digest emails
5. **Delivery Confirmation**: Track user acknowledgment of alerts
6. **A/B Testing**: Test different message formats
7. **Cost Tracking**: Track API costs per channel

## Related Files

- `services/alerts/delivery_engine.py` - Main implementation
- `services/alerts/test_delivery_engine.py` - Integration tests
- `services/alerts/channels/` - Individual channel implementations
- `shared/database/models.py` - AlertDeliveryLog model
- `services/alerts/matcher.py` - Alert rule matching logic
