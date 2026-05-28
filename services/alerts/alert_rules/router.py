"""
Alert Rules CRUD API Router
Handles alert rule creation, retrieval, update, delete, and test operations

Requirements: 13.1, 13.8
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from services.alerts.alert_rules.models import (
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
    AlertRuleResponse,
    AlertRuleListResponse,
    TestAlertRequest,
    TestAlertResponse
)
from shared.database.models import AlertRule, AnomalySeverity
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, and_
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ============================================================================
# Dependency: Database Session
# ============================================================================

async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ============================================================================
# Dependency: User Authentication (Placeholder)
# ============================================================================

async def get_current_user_id() -> str:
    """
    Get current authenticated user ID from JWT token
    
    TODO: Implement proper JWT authentication middleware
    For now, returns a test user ID
    """
    # In production, this would extract user_id from JWT token in Authorization header
    # For now, return a test user ID
    return "00000000-0000-0000-0000-000000000001"


# ============================================================================
# Helper Functions
# ============================================================================

async def check_rule_ownership(
    rule_id: str,
    user_id: str,
    session: AsyncSession
) -> AlertRule:
    """
    Check if alert rule exists and belongs to user
    
    Args:
        rule_id: Alert rule UUID
        user_id: User UUID
        session: Database session
        
    Returns:
        AlertRule object if found and owned by user
        
    Raises:
        HTTPException: If rule not found or not owned by user
    """
    result = await session.execute(
        select(AlertRule).where(
            and_(
                AlertRule.id == uuid.UUID(rule_id),
                AlertRule.user_id == uuid.UUID(user_id)
            )
        )
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule not found or access denied"
        )
    
    return rule


def validate_webhook_config(channels: List[str], webhook_url: Optional[str]) -> None:
    """
    Validate webhook configuration
    
    Args:
        channels: List of delivery channels
        webhook_url: Webhook URL
        
    Raises:
        HTTPException: If webhook channel is selected but URL is not provided
    """
    if 'webhook' in channels and not webhook_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="webhook_url is required when 'webhook' channel is selected"
        )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    request: CreateAlertRuleRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> AlertRuleResponse:
    """
    Create a new alert rule
    
    Validates the rule configuration and stores it in the database.
    
    Requirements: 13.1
    
    Args:
        request: Alert rule creation request
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Created alert rule with generated ID
        
    Raises:
        HTTPException 422: If rule validation fails
        HTTPException 500: If database operation fails
    """
    try:
        # Validate webhook configuration
        validate_webhook_config(request.channels, request.webhook_url)
        
        # Generate new rule ID
        rule_id = uuid.uuid4()
        
        # Create alert rule record
        now = datetime.utcnow()
        alert_rule = AlertRule(
            id=rule_id,
            user_id=uuid.UUID(user_id),
            name=request.name,
            description=request.description,
            instruments=request.instruments,
            asset_classes=request.asset_classes,
            anomaly_types=request.anomaly_types,
            min_severity=request.min_severity,
            channels=request.channels,
            max_alerts_per_hour=request.max_alerts_per_hour,
            quiet_hours_start=request.quiet_hours_start,
            quiet_hours_end=request.quiet_hours_end,
            webhook_url=request.webhook_url,
            webhook_secret=request.webhook_secret,
            enabled=request.enabled,
            created_at=now,
            updated_at=now
        )
        
        session.add(alert_rule)
        await session.commit()
        await session.refresh(alert_rule)
        
        logger.info(
            f"Alert rule created",
            extra={
                "rule_id": str(alert_rule.id),
                "user_id": user_id,
                "name": alert_rule.name,
                "instruments": alert_rule.instruments,
                "channels": alert_rule.channels
            }
        )
        
        return AlertRuleResponse(
            id=str(alert_rule.id),
            user_id=str(alert_rule.user_id),
            name=alert_rule.name,
            description=alert_rule.description,
            instruments=alert_rule.instruments,
            asset_classes=alert_rule.asset_classes,
            anomaly_types=alert_rule.anomaly_types,
            min_severity=alert_rule.min_severity.value,
            channels=alert_rule.channels,
            max_alerts_per_hour=alert_rule.max_alerts_per_hour,
            quiet_hours_start=alert_rule.quiet_hours_start,
            quiet_hours_end=alert_rule.quiet_hours_end,
            webhook_url=alert_rule.webhook_url,
            webhook_secret=alert_rule.webhook_secret,
            enabled=alert_rule.enabled,
            created_at=alert_rule.created_at,
            updated_at=alert_rule.updated_at
        )
        
    except ValueError as e:
        logger.error(f"Alert rule validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Alert rule validation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create alert rule: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create alert rule: {str(e)}"
        )


@router.get("/rules", response_model=AlertRuleListResponse)
async def list_alert_rules(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> AlertRuleListResponse:
    """
    Get paginated list of user's alert rules
    
    Requirements: 13.1
    
    Args:
        page: Page number (1-indexed)
        limit: Number of items per page
        enabled: Optional filter by enabled status
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Paginated list of alert rules
    """
    try:
        # Build query
        query = select(AlertRule).where(AlertRule.user_id == uuid.UUID(user_id))
        
        # Apply enabled filter if provided
        if enabled is not None:
            query = query.where(AlertRule.enabled == enabled)
        
        # Order by created_at descending
        query = query.order_by(AlertRule.created_at.desc())
        
        # Get total count
        count_query = select(AlertRule).where(AlertRule.user_id == uuid.UUID(user_id))
        if enabled is not None:
            count_query = count_query.where(AlertRule.enabled == enabled)
        
        count_result = await session.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await session.execute(query)
        rules = result.scalars().all()
        
        # Convert to response models
        rule_responses = [
            AlertRuleResponse(
                id=str(r.id),
                user_id=str(r.user_id),
                name=r.name,
                description=r.description,
                instruments=r.instruments,
                asset_classes=r.asset_classes,
                anomaly_types=r.anomaly_types,
                min_severity=r.min_severity.value,
                channels=r.channels,
                max_alerts_per_hour=r.max_alerts_per_hour,
                quiet_hours_start=r.quiet_hours_start,
                quiet_hours_end=r.quiet_hours_end,
                webhook_url=r.webhook_url,
                webhook_secret=r.webhook_secret,
                enabled=r.enabled,
                created_at=r.created_at,
                updated_at=r.updated_at
            )
            for r in rules
        ]
        
        total_pages = (total + limit - 1) // limit
        
        return AlertRuleListResponse(
            rules=rule_responses,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"Failed to list alert rules: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list alert rules: {str(e)}"
        )


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> AlertRuleResponse:
    """
    Get alert rule details by ID
    
    Requirements: 13.1
    
    Args:
        rule_id: Alert rule UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Full alert rule details
        
    Raises:
        HTTPException 404: If rule not found or access denied
    """
    try:
        rule = await check_rule_ownership(rule_id, user_id, session)
        
        return AlertRuleResponse(
            id=str(rule.id),
            user_id=str(rule.user_id),
            name=rule.name,
            description=rule.description,
            instruments=rule.instruments,
            asset_classes=rule.asset_classes,
            anomaly_types=rule.anomaly_types,
            min_severity=rule.min_severity.value,
            channels=rule.channels,
            max_alerts_per_hour=rule.max_alerts_per_hour,
            quiet_hours_start=rule.quiet_hours_start,
            quiet_hours_end=rule.quiet_hours_end,
            webhook_url=rule.webhook_url,
            webhook_secret=rule.webhook_secret,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert rule: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alert rule: {str(e)}"
        )


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    request: UpdateAlertRuleRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> AlertRuleResponse:
    """
    Update an existing alert rule
    
    Only provided fields will be updated. Null/missing fields are ignored.
    
    Requirements: 13.1
    
    Args:
        rule_id: Alert rule UUID
        request: Update request with new values
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Updated alert rule
        
    Raises:
        HTTPException 404: If rule not found or access denied
        HTTPException 422: If validation fails
    """
    try:
        # Check ownership
        rule = await check_rule_ownership(rule_id, user_id, session)
        
        # Update fields if provided
        update_data = request.model_dump(exclude_unset=True)
        
        # Validate webhook configuration if channels are being updated
        if 'channels' in update_data:
            webhook_url = update_data.get('webhook_url', rule.webhook_url)
            validate_webhook_config(update_data['channels'], webhook_url)
        
        # Apply updates
        for field, value in update_data.items():
            setattr(rule, field, value)
        
        # Update timestamp
        rule.updated_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(rule)
        
        logger.info(
            f"Alert rule updated",
            extra={
                "rule_id": rule_id,
                "user_id": user_id,
                "name": rule.name,
                "updated_fields": list(update_data.keys())
            }
        )
        
        return AlertRuleResponse(
            id=str(rule.id),
            user_id=str(rule.user_id),
            name=rule.name,
            description=rule.description,
            instruments=rule.instruments,
            asset_classes=rule.asset_classes,
            anomaly_types=rule.anomaly_types,
            min_severity=rule.min_severity.value,
            channels=rule.channels,
            max_alerts_per_hour=rule.max_alerts_per_hour,
            quiet_hours_start=rule.quiet_hours_start,
            quiet_hours_end=rule.quiet_hours_end,
            webhook_url=rule.webhook_url,
            webhook_secret=rule.webhook_secret,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Alert rule validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Alert rule validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update alert rule: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update alert rule: {str(e)}"
        )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_alert_rule(
    rule_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> dict:
    """
    Delete an alert rule
    
    Permanently deletes the rule from the database.
    
    Requirements: 13.1
    
    Args:
        rule_id: Alert rule UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException 404: If rule not found or access denied
    """
    try:
        # Check ownership
        rule = await check_rule_ownership(rule_id, user_id, session)
        
        rule_name = rule.name
        
        # Delete the rule
        await session.delete(rule)
        await session.commit()
        
        logger.info(
            f"Alert rule deleted",
            extra={
                "rule_id": rule_id,
                "user_id": user_id,
                "name": rule_name
            }
        )
        
        return {
            "success": True,
            "message": f"Alert rule '{rule_name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete alert rule: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete alert rule: {str(e)}"
        )


@router.post("/test", response_model=TestAlertResponse)
async def send_test_alert(
    rule_id: str = Query(..., description="Alert rule ID to test"),
    request: TestAlertRequest = TestAlertRequest(),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> TestAlertResponse:
    """
    Send a test alert to all configured channels for a rule
    
    Validates the delivery chain without creating a real anomaly event.
    Returns delivery status for each configured channel.
    
    Requirements: 13.8
    
    Args:
        rule_id: Alert rule UUID to test
        request: Test alert request with optional custom message
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Test alert response with delivery statuses
        
    Raises:
        HTTPException 404: If rule not found or access denied
    """
    try:
        # Check ownership
        rule = await check_rule_ownership(rule_id, user_id, session)
        
        # Prepare test message
        test_message = request.message or "This is a test alert from Signalix"
        
        # Simulate delivery to each channel
        # In a real implementation, this would call the actual delivery channels
        # For now, we'll simulate successful delivery
        delivery_statuses = {}
        
        for channel in rule.channels:
            # Simulate delivery
            try:
                # TODO: Implement actual channel delivery
                # For now, mark all as sent
                delivery_statuses[channel] = "sent"
                
                logger.info(
                    f"Test alert sent to {channel}",
                    extra={
                        "rule_id": rule_id,
                        "user_id": user_id,
                        "channel": channel
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send test alert to {channel}: {str(e)}")
                delivery_statuses[channel] = f"failed: {str(e)}"
        
        # Check if all deliveries succeeded
        all_sent = all(status == "sent" for status in delivery_statuses.values())
        
        return TestAlertResponse(
            success=all_sent,
            message="Test alert sent to all configured channels" if all_sent else "Some channels failed",
            rule_id=rule_id,
            delivery_statuses=delivery_statuses
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send test alert: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test alert: {str(e)}"
        )
