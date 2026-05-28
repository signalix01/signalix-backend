"""
Unit tests for Alert Rules CRUD operations

Requirements: 13.1, 13.8
"""
import pytest
from services.alerts.alert_rules.models import (
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
    TestAlertRequest
)
from shared.database.models import AnomalySeverity
import uuid


class TestAlertRuleModels:
    """Test Pydantic model validation"""
    
    def test_create_alert_rule_request_valid(self):
        """Test valid alert rule creation request"""
        request = CreateAlertRuleRequest(
            name="Test Rule",
            description="Test description",
            instruments=["BANKNIFTY"],
            asset_classes=["fo"],
            anomaly_types=["flash_crash", "whale_movement"],
            min_severity=AnomalySeverity.HIGH,
            channels=["in_app", "push"],
            max_alerts_per_hour=10,
            quiet_hours_start="22:00",
            quiet_hours_end="08:00",
            enabled=True
        )
        
        assert request.name == "Test Rule"
        assert request.instruments == ["BANKNIFTY"]
        assert request.asset_classes == ["fo"]
        assert request.anomaly_types == ["flash_crash", "whale_movement"]
        assert request.min_severity == AnomalySeverity.HIGH
        assert request.channels == ["in_app", "push"]
        assert request.max_alerts_per_hour == 10
        assert request.enabled is True
    
    def test_create_alert_rule_request_invalid_asset_class(self):
        """Test invalid asset class validation"""
        with pytest.raises(ValueError, match="Invalid asset class"):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["invalid_class"],
                anomaly_types=["flash_crash"],
                channels=["in_app"]
            )
    
    def test_create_alert_rule_request_invalid_anomaly_type(self):
        """Test invalid anomaly type validation"""
        with pytest.raises(ValueError, match="Invalid anomaly type"):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["fo"],
                anomaly_types=["invalid_type"],
                channels=["in_app"]
            )
    
    def test_create_alert_rule_request_invalid_channel(self):
        """Test invalid channel validation"""
        with pytest.raises(ValueError, match="Invalid channel"):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["fo"],
                anomaly_types=["flash_crash"],
                channels=["invalid_channel"]
            )
    
    def test_create_alert_rule_request_quiet_hours_validation(self):
        """Test quiet hours validation"""
        with pytest.raises(ValueError, match="quiet_hours_start must be provided"):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["fo"],
                anomaly_types=["flash_crash"],
                channels=["in_app"],
                quiet_hours_end="08:00"  # Missing start time
            )
    
    def test_create_alert_rule_request_all_instruments(self):
        """Test ALL instruments filter"""
        request = CreateAlertRuleRequest(
            name="Test Rule",
            instruments=["ALL"],
            asset_classes=["equity"],
            anomaly_types=["price_spike"],
            channels=["in_app"]
        )
        
        assert request.instruments == ["ALL"]
    
    def test_update_alert_rule_request_partial(self):
        """Test partial update request"""
        request = UpdateAlertRuleRequest(
            name="Updated Name",
            enabled=False
        )
        
        assert request.name == "Updated Name"
        assert request.enabled is False
        assert request.instruments is None  # Not provided
        assert request.channels is None  # Not provided


class TestAlertRuleValidation:
    """Test validation logic"""
    
    def test_webhook_validation_missing_url(self):
        """Test webhook channel requires URL"""
        # This should fail when webhook is in channels but no URL provided
        request_data = {
            "name": "Test Rule",
            "instruments": ["BANKNIFTY"],
            "asset_classes": ["fo"],
            "anomaly_types": ["flash_crash"],
            "channels": ["webhook"],  # Webhook selected
            # webhook_url is missing
        }
        
        # The validation happens in the endpoint, not the model
        # So we test the endpoint behavior
        # This is tested in integration tests
        pass
    
    def test_max_alerts_per_hour_bounds(self):
        """Test max_alerts_per_hour bounds"""
        # Test minimum
        with pytest.raises(ValueError):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["fo"],
                anomaly_types=["flash_crash"],
                channels=["in_app"],
                max_alerts_per_hour=0  # Below minimum
            )
        
        # Test maximum
        with pytest.raises(ValueError):
            CreateAlertRuleRequest(
                name="Test Rule",
                instruments=["BANKNIFTY"],
                asset_classes=["fo"],
                anomaly_types=["flash_crash"],
                channels=["in_app"],
                max_alerts_per_hour=101  # Above maximum
            )
        
        # Test valid range
        request = CreateAlertRuleRequest(
            name="Test Rule",
            instruments=["BANKNIFTY"],
            asset_classes=["fo"],
            anomaly_types=["flash_crash"],
            channels=["in_app"],
            max_alerts_per_hour=50  # Valid
        )
        assert request.max_alerts_per_hour == 50


class TestAlertRuleExamples:
    """Test example configurations"""
    
    def test_banknifty_critical_alerts(self):
        """Test BankNifty critical alerts configuration"""
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
        
        assert request.name == "BankNifty Critical Alerts"
        assert "flash_crash" in request.anomaly_types
        assert "telegram" in request.channels
    
    def test_crypto_whale_tracker(self):
        """Test crypto whale tracking configuration"""
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
        
        assert request.asset_classes == ["crypto"]
        assert "whale_movement" in request.anomaly_types
        assert request.webhook_url is not None
    
    def test_all_instruments_monitor(self):
        """Test monitoring all watchlisted instruments"""
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
        
        assert request.instruments == ["ALL"]
        assert request.min_severity == AnomalySeverity.CRITICAL
        assert "sms" in request.channels


class TestTestAlertRequest:
    """Test alert testing functionality"""
    
    def test_test_alert_default_message(self):
        """Test default test alert message"""
        request = TestAlertRequest()
        assert request.message == "This is a test alert from Signalix"
    
    def test_test_alert_custom_message(self):
        """Test custom test alert message"""
        request = TestAlertRequest(
            message="Testing BankNifty alerts"
        )
        assert request.message == "Testing BankNifty alerts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
