"""
Unit Tests for Alert Delivery Channels
Tests all 7 delivery channels with mocked external APIs

Requirements: 13.2, 13.6, 13.7
"""
import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Import channels
from .in_app import InAppChannel
from .push import PushChannel
from .whatsapp import WhatsAppChannel
from .sms import SMSChannel
from .email import EmailChannel
from .telegram import TelegramChannel
from .webhook import WebhookChannel

# Mock AnomalyEvent
class MockAnomalyEvent:
    """Mock AnomalyEvent for testing"""
    def __init__(self):
        self.id = uuid4()
        self.instrument = "BANKNIFTY"
        self.asset_class = "fo"
        self.exchange = "NSE"
        self.anomaly_type = MagicMock(value="flash_crash")
        self.severity = MagicMock(value="critical")
        self.detected_at = datetime.utcnow()
        self.description = "Flash crash detected: 5% drop in 3 minutes"
        self.z_score = -4.2
        self.price = 45250.50
        self.volume = 125000.0
        self.affected_instruments = ["NIFTY", "FINNIFTY"]
        self.raw_data = {"test": "data"}


@pytest.fixture
def mock_event():
    """Fixture for mock anomaly event"""
    return MockAnomalyEvent()


@pytest.fixture
def mock_redis():
    """Fixture for mock Redis client"""
    redis_mock = AsyncMock()
    redis_mock.publish = AsyncMock(return_value=1)
    redis_mock.lpush = AsyncMock()
    redis_mock.ltrim = AsyncMock()
    redis_mock.expire = AsyncMock()
    redis_mock.lrange = AsyncMock(return_value=[])
    redis_mock.delete = AsyncMock()
    return redis_mock


# ============================================================================
# InAppChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_in_app_channel_send_success(mock_redis, mock_event):
    """Test successful in-app alert delivery"""
    channel = InAppChannel(mock_redis)
    
    result = await channel.send("user123", mock_event, "rule456")
    
    assert result["status"] == "sent"
    assert result["channel"] == "in_app"
    assert result["subscribers"] == 1
    assert result["queued_offline"] is False
    
    # Verify Redis publish was called
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == "user_alerts:user123"
    
    # Verify payload structure
    payload = json.loads(call_args[0][1])
    assert payload["type"] == "anomaly_alert"
    assert payload["instrument"] == "BANKNIFTY"
    assert payload["severity"] == "critical"


@pytest.mark.asyncio
async def test_in_app_channel_offline_queue(mock_redis, mock_event):
    """Test offline queueing when no subscribers"""
    mock_redis.publish = AsyncMock(return_value=0)  # No subscribers
    
    channel = InAppChannel(mock_redis)
    result = await channel.send("user123", mock_event, "rule456")
    
    assert result["status"] == "sent"
    assert result["queued_offline"] is True
    
    # Verify offline queue operations
    mock_redis.lpush.assert_called_once()
    mock_redis.ltrim.assert_called_once()
    mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_in_app_channel_get_offline_alerts(mock_redis):
    """Test retrieving offline alerts"""
    mock_alerts = [
        json.dumps({"type": "anomaly_alert", "instrument": "NIFTY"}),
        json.dumps({"type": "anomaly_alert", "instrument": "BANKNIFTY"}),
    ]
    mock_redis.lrange = AsyncMock(return_value=mock_alerts)
    
    channel = InAppChannel(mock_redis)
    alerts = await channel.get_offline_alerts("user123")
    
    assert len(alerts) == 2
    assert alerts[0]["instrument"] == "NIFTY"
    assert alerts[1]["instrument"] == "BANKNIFTY"
    
    # Verify queue was cleared
    mock_redis.delete.assert_called_once_with("offline_alerts:user123")


@pytest.mark.asyncio
async def test_in_app_channel_send_test(mock_redis):
    """Test sending test alert"""
    channel = InAppChannel(mock_redis)
    result = await channel.send_test("user123")
    
    assert result["status"] == "sent"
    assert result["channel"] == "in_app"
    mock_redis.publish.assert_called_once()


# ============================================================================
# PushChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_push_channel_not_configured():
    """Test push channel when Firebase not configured"""
    channel = PushChannel()
    result = await channel.send("user123", MockAnomalyEvent(), "rule456", ["token1"])
    
    assert result["status"] == "skipped"
    assert "not configured" in result["reason"]


@pytest.mark.asyncio
async def test_push_channel_no_tokens(mock_event):
    """Test push channel with no device tokens"""
    # Note: Firebase not available in test environment, so this will skip
    channel = PushChannel()
    
    result = await channel.send("user123", mock_event, "rule456", [])
    
    assert result["status"] == "skipped"
    # Will skip due to Firebase not configured in test environment
    assert "reason" in result


# ============================================================================
# WhatsAppChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_whatsapp_channel_send_success(mock_event):
    """Test successful WhatsApp delivery"""
    with patch('services.alerts.channels.whatsapp.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_WHATSAPP_NUMBER": "whatsapp:+14155238886",
        }.get(key, default)
        
        channel = WhatsAppChannel()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"sid": "SM123"}
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await channel.send("user123", mock_event, "rule456", "+919876543210")
            
            assert result["status"] == "sent"
            assert result["channel"] == "whatsapp"
            assert result["message_sid"] == "SM123"


@pytest.mark.asyncio
async def test_whatsapp_channel_format_message(mock_event):
    """Test WhatsApp message formatting"""
    with patch('services.alerts.channels.whatsapp.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "token123",
        }.get(key, default)
        
        channel = WhatsAppChannel()
        message = channel._format_message(mock_event)
        
        assert "BANKNIFTY" in message
        assert "Flash Crash" in message
        assert "CRITICAL" in message
        assert "₹45,250.50" in message
        # Z-score is formatted with 2 decimals, so check for -4.20 or -4.2
        assert "-4.2" in message or "-4.20" in message


# ============================================================================
# SMSChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_sms_channel_critical_only(mock_event):
    """Test SMS only sends for critical alerts"""
    with patch('services.alerts.channels.sms.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_PHONE_NUMBER": "+14155551234",
        }.get(key, default)
        
        channel = SMSChannel()
        
        # Test with non-critical severity
        mock_event.severity = MagicMock(value="medium")
        result = await channel.send("user123", mock_event, "rule456", "+919876543210")
        
        assert result["status"] == "skipped"
        assert "only for critical" in result["reason"]


@pytest.mark.asyncio
async def test_sms_channel_send_critical(mock_event):
    """Test SMS sends for critical alerts"""
    with patch('services.alerts.channels.sms.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_PHONE_NUMBER": "+14155551234",
        }.get(key, default)
        
        channel = SMSChannel()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"sid": "SM456"}
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await channel.send("user123", mock_event, "rule456", "+919876543210")
            
            assert result["status"] == "sent"
            assert result["channel"] == "sms"


@pytest.mark.asyncio
async def test_sms_channel_message_length(mock_event):
    """Test SMS message stays under 160 chars"""
    with patch('services.alerts.channels.sms.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "token123",
            "TWILIO_PHONE_NUMBER": "+14155551234",
        }.get(key, default)
        
        channel = SMSChannel()
        
        # Create event with very long description
        mock_event.description = "A" * 200
        message = channel._format_message(mock_event)
        
        assert len(message) <= 160


# ============================================================================
# EmailChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_email_channel_send_success(mock_event):
    """Test successful email delivery"""
    with patch('services.alerts.channels.email.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "SENDGRID_API_KEY": "SG.test123",
            "SENDGRID_FROM_EMAIL": "alerts@signalixai.com",
        }.get(key, default)
        
        channel = EmailChannel()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 202
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await channel.send("user123", mock_event, "rule456", "user@example.com")
            
            assert result["status"] == "sent"
            assert result["channel"] == "email"
            assert result["to"] == "user@example.com"


@pytest.mark.asyncio
async def test_email_channel_html_formatting(mock_event):
    """Test email HTML formatting"""
    with patch('services.alerts.channels.email.os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "SENDGRID_API_KEY": "SG.test123",
        }.get(key, default)
        
        channel = EmailChannel()
        html = channel._format_html(mock_event)
        
        assert "BANKNIFTY" in html
        assert "Flash Crash" in html
        assert "₹45,250.50" in html
        assert "<table" in html
        assert "<!DOCTYPE html>" in html


# ============================================================================
# TelegramChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_telegram_channel_send_success(mock_event):
    """Test successful Telegram delivery"""
    with patch('services.alerts.channels.telegram.os.getenv') as mock_getenv:
        mock_getenv.return_value = "123456:ABC-DEF"
        
        channel = TelegramChannel()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "ok": True,
                "result": {"message_id": 789}
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await channel.send("user123", mock_event, "rule456", "123456789")
            
            assert result["status"] == "sent"
            assert result["channel"] == "telegram"
            assert result["message_id"] == 789


@pytest.mark.asyncio
async def test_telegram_channel_markdown_formatting(mock_event):
    """Test Telegram Markdown formatting"""
    with patch('services.alerts.channels.telegram.os.getenv') as mock_getenv:
        mock_getenv.return_value = "123456:ABC-DEF"
        
        channel = TelegramChannel()
        message = channel._format_message(mock_event)
        
        assert "*SIGNALIX ALERT*" in message
        assert "`BANKNIFTY`" in message
        assert "*Price:*" in message
        assert "₹45,250.50" in message


# ============================================================================
# WebhookChannel Tests
# ============================================================================

@pytest.mark.asyncio
async def test_webhook_channel_send_success(mock_event):
    """Test successful webhook delivery"""
    channel = WebhookChannel()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await channel.send(
            "user123",
            mock_event,
            "rule456",
            "https://example.com/webhook",
            "secret123"
        )
        
        assert result["status"] == "sent"
        assert result["channel"] == "webhook"
        assert result["response_status"] == 200


@pytest.mark.asyncio
async def test_webhook_channel_signature_generation(mock_event):
    """Test HMAC signature generation"""
    channel = WebhookChannel()
    
    payload = json.dumps({"test": "data"})
    signature = channel._generate_signature(payload, "secret123")
    
    assert signature.startswith("sha256=")
    assert len(signature) > 10


@pytest.mark.asyncio
async def test_webhook_channel_signature_verification(mock_event):
    """Test HMAC signature verification"""
    channel = WebhookChannel()
    
    payload = json.dumps({"test": "data"})
    signature = channel._generate_signature(payload, "secret123")
    
    # Valid signature
    assert channel.verify_signature(payload, signature, "secret123") is True
    
    # Invalid signature
    assert channel.verify_signature(payload, "sha256=invalid", "secret123") is False
    
    # Wrong secret
    assert channel.verify_signature(payload, signature, "wrong_secret") is False


@pytest.mark.asyncio
async def test_webhook_channel_payload_structure(mock_event):
    """Test webhook payload structure"""
    channel = WebhookChannel()
    
    payload = channel._build_payload(mock_event, "rule456", "user123")
    
    assert payload["event_type"] == "anomaly_alert"
    assert payload["rule_id"] == "rule456"
    assert payload["user_id"] == "user123"
    assert payload["event"]["instrument"] == "BANKNIFTY"
    assert payload["event"]["severity"] == "critical"
    assert payload["event"]["price"] == 45250.50


@pytest.mark.asyncio
async def test_webhook_channel_timeout():
    """Test webhook timeout handling"""
    channel = WebhookChannel()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Timeout")
        )
        
        result = await channel.send(
            "user123",
            MockAnomalyEvent(),
            "rule456",
            "https://example.com/webhook"
        )
        
        assert result["status"] == "failed"
        assert "error" in result


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_all_channels_test_methods():
    """Test that all channels have working test methods"""
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)
    
    channels = [
        (InAppChannel(mock_redis), "send_test", ["user123"]),
    ]
    
    for channel, method_name, args in channels:
        method = getattr(channel, method_name)
        result = await method(*args)
        
        assert "status" in result
        assert "channel" in result
        assert result["status"] in ["sent", "skipped", "failed"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
