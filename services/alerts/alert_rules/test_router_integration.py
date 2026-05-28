"""
Integration tests for Alert Rules Router
Tests the full CRUD flow with database

Requirements: 13.1, 13.8
"""
import pytest
import asyncio
from services.alerts.alert_rules.models import (
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
    TestAlertRequest
)
from shared.database.models import AlertRule, AnomalySeverity, Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
import uuid
import os


# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test"
)


@pytest.fixture(scope="function")
async def db_session():
    """Create a test database session"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_alert_rule(db_session):
    """Test creating an alert rule"""
    # Create test user ID
    user_id = uuid.uuid4()
    
    # Create alert rule
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=user_id,
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
        webhook_url=None,
        webhook_secret=None,
        enabled=True
    )
    
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    
    # Verify
    assert rule.id is not None
    assert rule.name == "Test Rule"
    assert rule.instruments == ["BANKNIFTY"]
    assert rule.asset_classes == ["fo"]
    assert rule.min_severity == AnomalySeverity.HIGH
    assert rule.enabled is True


@pytest.mark.asyncio
async def test_list_alert_rules(db_session):
    """Test listing alert rules"""
    user_id = uuid.uuid4()
    
    # Create multiple rules
    for i in range(3):
        rule = AlertRule(
            id=uuid.uuid4(),
            user_id=user_id,
            name=f"Test Rule {i}",
            instruments=["BANKNIFTY"],
            asset_classes=["fo"],
            anomaly_types=["flash_crash"],
            min_severity=AnomalySeverity.MEDIUM,
            channels=["in_app"],
            max_alerts_per_hour=10,
            enabled=True
        )
        db_session.add(rule)
    
    await db_session.commit()
    
    # Query rules
    result = await db_session.execute(
        select(AlertRule).where(AlertRule.user_id == user_id)
    )
    rules = result.scalars().all()
    
    assert len(rules) == 3
    assert all(r.user_id == user_id for r in rules)


@pytest.mark.asyncio
async def test_update_alert_rule(db_session):
    """Test updating an alert rule"""
    user_id = uuid.uuid4()
    
    # Create rule
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Original Name",
        instruments=["BANKNIFTY"],
        asset_classes=["fo"],
        anomaly_types=["flash_crash"],
        min_severity=AnomalySeverity.MEDIUM,
        channels=["in_app"],
        max_alerts_per_hour=10,
        enabled=True
    )
    
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    
    # Update rule
    rule.name = "Updated Name"
    rule.enabled = False
    await db_session.commit()
    await db_session.refresh(rule)
    
    # Verify
    assert rule.name == "Updated Name"
    assert rule.enabled is False


@pytest.mark.asyncio
async def test_delete_alert_rule(db_session):
    """Test deleting an alert rule"""
    user_id = uuid.uuid4()
    
    # Create rule
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Test Rule",
        instruments=["BANKNIFTY"],
        asset_classes=["fo"],
        anomaly_types=["flash_crash"],
        min_severity=AnomalySeverity.MEDIUM,
        channels=["in_app"],
        max_alerts_per_hour=10,
        enabled=True
    )
    
    db_session.add(rule)
    await db_session.commit()
    rule_id = rule.id
    
    # Delete rule
    await db_session.delete(rule)
    await db_session.commit()
    
    # Verify deletion
    result = await db_session.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    deleted_rule = result.scalar_one_or_none()
    
    assert deleted_rule is None


@pytest.mark.asyncio
async def test_filter_by_enabled(db_session):
    """Test filtering rules by enabled status"""
    user_id = uuid.uuid4()
    
    # Create enabled and disabled rules
    for i in range(2):
        rule = AlertRule(
            id=uuid.uuid4(),
            user_id=user_id,
            name=f"Enabled Rule {i}",
            instruments=["BANKNIFTY"],
            asset_classes=["fo"],
            anomaly_types=["flash_crash"],
            min_severity=AnomalySeverity.MEDIUM,
            channels=["in_app"],
            max_alerts_per_hour=10,
            enabled=True
        )
        db_session.add(rule)
    
    for i in range(3):
        rule = AlertRule(
            id=uuid.uuid4(),
            user_id=user_id,
            name=f"Disabled Rule {i}",
            instruments=["BANKNIFTY"],
            asset_classes=["fo"],
            anomaly_types=["flash_crash"],
            min_severity=AnomalySeverity.MEDIUM,
            channels=["in_app"],
            max_alerts_per_hour=10,
            enabled=False
        )
        db_session.add(rule)
    
    await db_session.commit()
    
    # Query enabled rules
    result = await db_session.execute(
        select(AlertRule).where(
            AlertRule.user_id == user_id,
            AlertRule.enabled == True
        )
    )
    enabled_rules = result.scalars().all()
    
    # Query disabled rules
    result = await db_session.execute(
        select(AlertRule).where(
            AlertRule.user_id == user_id,
            AlertRule.enabled == False
        )
    )
    disabled_rules = result.scalars().all()
    
    assert len(enabled_rules) == 2
    assert len(disabled_rules) == 3


@pytest.mark.asyncio
async def test_webhook_configuration(db_session):
    """Test webhook configuration"""
    user_id = uuid.uuid4()
    
    # Create rule with webhook
    rule = AlertRule(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Webhook Rule",
        instruments=["BANKNIFTY"],
        asset_classes=["fo"],
        anomaly_types=["flash_crash"],
        min_severity=AnomalySeverity.HIGH,
        channels=["webhook"],
        webhook_url="https://api.example.com/webhook",
        webhook_secret="secret123",
        max_alerts_per_hour=10,
        enabled=True
    )
    
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    
    # Verify
    assert rule.webhook_url == "https://api.example.com/webhook"
    assert rule.webhook_secret == "secret123"
    assert "webhook" in rule.channels


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
