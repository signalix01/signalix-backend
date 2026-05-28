# Alert Rules CRUD API

## Overview

This module implements the Alert Rules CRUD API for the Signalix Alert Engine. It allows users to configure alert rules that specify which instruments, anomaly types, severity levels, and delivery channels to use for receiving alerts.

**Requirements:** 13.1, 13.8

## Features

- ✅ Create alert rules with full configuration
- ✅ List user's alert rules with pagination and filtering
- ✅ Get individual alert rule details
- ✅ Update alert rules (partial updates supported)
- ✅ Delete alert rules
- ✅ Send test alerts to validate delivery channels
- ✅ Comprehensive validation for all fields
- ✅ Webhook configuration with HMAC secret support
- ✅ Quiet hours configuration (IST timezone)
- ✅ Rate limiting configuration

## API Endpoints

### 1. Create Alert Rule

**POST** `/api/v1/alerts/rules`

Creates a new alert rule with the specified configuration.

**Request Body:**
```json
{
  "name": "BankNifty Critical Alerts",
  "description": "Critical alerts for BankNifty movements",
  "instruments": ["BANKNIFTY"],
  "asset_classes": ["fo"],
  "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
  "min_severity": "high",
  "channels": ["in_app", "push", "telegram"],
  "max_alerts_per_hour": 10,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "webhook_url": null,
  "webhook_secret": null,
  "enabled": true
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "00000000-0000-0000-0000-000000000001",
  "name": "BankNifty Critical Alerts",
  "description": "Critical alerts for BankNifty movements",
  "instruments": ["BANKNIFTY"],
  "asset_classes": ["fo"],
  "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
  "min_severity": "high",
  "channels": ["in_app", "push", "telegram"],
  "max_alerts_per_hour": 10,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "webhook_url": null,
  "webhook_secret": null,
  "enabled": true,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

### 2. List Alert Rules

**GET** `/api/v1/alerts/rules?page=1&limit=10&enabled=true`

Returns a paginated list of the user's alert rules.

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 10, max: 100)
- `enabled` (optional): Filter by enabled status (true/false)

**Response:** `200 OK`
```json
{
  "rules": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "name": "BankNifty Critical Alerts",
      "description": "Critical alerts for BankNifty movements",
      "instruments": ["BANKNIFTY"],
      "asset_classes": ["fo"],
      "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
      "min_severity": "high",
      "channels": ["in_app", "push", "telegram"],
      "max_alerts_per_hour": 10,
      "quiet_hours_start": "22:00",
      "quiet_hours_end": "08:00",
      "webhook_url": null,
      "webhook_secret": null,
      "enabled": true,
      "created_at": "2025-01-15T10:00:00Z",
      "updated_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 10,
  "total_pages": 1
}
```

### 3. Get Alert Rule

**GET** `/api/v1/alerts/rules/{rule_id}`

Returns the full details of a specific alert rule.

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "00000000-0000-0000-0000-000000000001",
  "name": "BankNifty Critical Alerts",
  "description": "Critical alerts for BankNifty movements",
  "instruments": ["BANKNIFTY"],
  "asset_classes": ["fo"],
  "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
  "min_severity": "high",
  "channels": ["in_app", "push", "telegram"],
  "max_alerts_per_hour": 10,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "webhook_url": null,
  "webhook_secret": null,
  "enabled": true,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

### 4. Update Alert Rule

**PUT** `/api/v1/alerts/rules/{rule_id}`

Updates an existing alert rule. Only provided fields will be updated.

**Request Body:**
```json
{
  "name": "Updated Rule Name",
  "enabled": false
}
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "00000000-0000-0000-0000-000000000001",
  "name": "Updated Rule Name",
  "description": "Critical alerts for BankNifty movements",
  "instruments": ["BANKNIFTY"],
  "asset_classes": ["fo"],
  "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
  "min_severity": "high",
  "channels": ["in_app", "push", "telegram"],
  "max_alerts_per_hour": 10,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "webhook_url": null,
  "webhook_secret": null,
  "enabled": false,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

### 5. Delete Alert Rule

**DELETE** `/api/v1/alerts/rules/{rule_id}`

Permanently deletes an alert rule.

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Alert rule 'BankNifty Critical Alerts' deleted successfully"
}
```

### 6. Send Test Alert

**POST** `/api/v1/alerts/test?rule_id={rule_id}`

Sends a test alert to all configured channels for a rule to validate the delivery chain.

**Request Body:**
```json
{
  "message": "Testing BankNifty alerts"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Test alert sent to all configured channels",
  "rule_id": "550e8400-e29b-41d4-a716-446655440000",
  "delivery_statuses": {
    "in_app": "sent",
    "push": "sent",
    "telegram": "sent"
  }
}
```

## Validation Rules

### Asset Classes
Valid values: `equity`, `fo`, `crypto`, `forex`, `commodity`

### Anomaly Types
Valid values:
- `price_spike`
- `volume_surge`
- `volatility_explosion`
- `gap_up`
- `gap_down`
- `flash_crash`
- `flash_rally`
- `unusual_pattern`
- `whale_movement`
- `institutional_flow`
- `options_unusual`
- `correlation_break`
- `regime_change`

### Delivery Channels
Valid values: `in_app`, `push`, `email`, `whatsapp`, `sms`, `telegram`, `webhook`

**Note:** If `webhook` channel is selected, `webhook_url` must be provided.

### Severity Levels
Valid values: `low`, `medium`, `high`, `critical`

### Rate Limiting
- `max_alerts_per_hour`: Must be between 1 and 100
- CRITICAL severity alerts bypass rate limits

### Quiet Hours
- Format: `HH:MM` (24-hour format)
- Timezone: IST (Indian Standard Time)
- Both `quiet_hours_start` and `quiet_hours_end` must be provided together
- CRITICAL severity alerts bypass quiet hours

### Instruments
- Can be a list of specific instrument symbols: `["BANKNIFTY", "NIFTY"]`
- Or `["ALL"]` to monitor all watchlisted instruments

## Error Responses

### 404 Not Found
```json
{
  "detail": "Alert rule not found or access denied"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": "Alert rule validation failed: Invalid asset class: invalid_class. Must be one of {'equity', 'fo', 'crypto', 'forex', 'commodity'}"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to create alert rule: Database connection error"
}
```

## Usage Examples

### Example 1: BankNifty Critical Alerts
Monitor BankNifty for critical events with multiple delivery channels:

```python
request = CreateAlertRuleRequest(
    name="BankNifty Critical Alerts",
    description="Critical alerts for BankNifty movements",
    instruments=["BANKNIFTY"],
    asset_classes=["fo"],
    anomaly_types=["flash_crash", "flash_rally", "whale_movement"],
    min_severity=AnomalySeverity.HIGH,
    channels=["in_app", "push", "telegram"],
    max_alerts_per_hour=10,
    quiet_hours_start="22:00",
    quiet_hours_end="08:00",
    enabled=True
)
```

### Example 2: Crypto Whale Tracker
Track large BTC/ETH movements with webhook delivery:

```python
request = CreateAlertRuleRequest(
    name="Crypto Whale Tracker",
    description="Track large BTC/ETH movements",
    instruments=["BTCUSDT", "ETHUSDT"],
    asset_classes=["crypto"],
    anomaly_types=["whale_movement", "volume_surge"],
    min_severity=AnomalySeverity.MEDIUM,
    channels=["in_app", "webhook"],
    webhook_url="https://api.example.com/webhook",
    webhook_secret="secret123",
    max_alerts_per_hour=20,
    enabled=True
)
```

### Example 3: All Instruments Monitor
Monitor all watchlisted instruments for critical events:

```python
request = CreateAlertRuleRequest(
    name="All Instruments Monitor",
    description="Monitor all watchlisted instruments",
    instruments=["ALL"],
    asset_classes=["equity", "fo"],
    anomaly_types=["flash_crash", "flash_rally"],
    min_severity=AnomalySeverity.CRITICAL,
    channels=["in_app", "push", "sms"],
    max_alerts_per_hour=5,
    enabled=True
)
```

## Testing

### Unit Tests
Run unit tests for model validation:
```bash
pytest services/alerts/alert_rules/test_alert_rules.py -v
```

### Integration Tests
Run integration tests with database:
```bash
pytest services/alerts/alert_rules/test_router_integration.py -v
```

## Database Schema

The alert rules are stored in the `alert_rules` table:

```sql
CREATE TABLE alert_rules (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    instruments TEXT[] NOT NULL,
    asset_classes TEXT[] NOT NULL,
    anomaly_types TEXT[] NOT NULL,
    min_severity VARCHAR(20) NOT NULL,
    channels TEXT[] NOT NULL,
    max_alerts_per_hour INTEGER NOT NULL DEFAULT 10,
    quiet_hours_start VARCHAR(5),
    quiet_hours_end VARCHAR(5),
    webhook_url VARCHAR(500),
    webhook_secret VARCHAR(100),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_rules_user_id ON alert_rules(user_id);
CREATE INDEX idx_alert_rules_enabled ON alert_rules(enabled);
CREATE INDEX idx_alert_rules_user_enabled ON alert_rules(user_id, enabled);
```

## Next Steps

The following components need to be implemented to complete the alert delivery system:

1. **Alert Matching Engine** (Task 39)
   - Match anomaly events to alert rules
   - Apply quiet hours and rate limiting
   - Filter by severity and instrument

2. **Delivery Channels** (Task 40)
   - Implement in-app WebSocket delivery
   - Implement push notifications (FCM)
   - Implement WhatsApp (Twilio)
   - Implement SMS (Twilio)
   - Implement Email (SendGrid)
   - Implement Telegram Bot API
   - Implement Webhook with HMAC signature

3. **Alert Delivery Engine** (Task 41)
   - Orchestrate delivery across channels
   - Implement retry logic with exponential backoff
   - Log all delivery attempts
   - Handle offline users with queue

4. **WebSocket Endpoint** (Task 42)
   - Real-time alert streaming
   - Offline alert queue delivery
   - Latency monitoring

## Implementation Notes

- **Authentication:** Currently uses a placeholder `get_current_user_id()` function. In production, this should extract the user ID from a JWT token.
- **Test Alert Delivery:** The test alert endpoint currently simulates delivery. Actual channel delivery will be implemented in Task 40.
- **Webhook Security:** Webhook deliveries will include an `X-Signalix-Signature` HMAC-SHA256 header for request authenticity verification (implemented in Task 40).
- **Database Connection:** Uses the same database connection pattern as other services in the codebase.

## Files

- `models.py` - Pydantic request/response models
- `router.py` - FastAPI router with all CRUD endpoints
- `test_alert_rules.py` - Unit tests for model validation
- `test_router_integration.py` - Integration tests with database
- `README.md` - This documentation file
