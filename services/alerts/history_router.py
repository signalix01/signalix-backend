"""
Alert History API Router
Provides historical access to anomaly events and delivery logs

Task 43: Implement alert history API
Requirements: Standard API for historical alert access
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field, UUID4
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from shared.database.models import (
    AnomalyEvent,
    AlertDeliveryLog,
    AnomalyType,
    AnomalySeverity,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, and_, desc, func
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
    return "00000000-0000-0000-0000-000000000001"


# ============================================================================
# Response Models
# ============================================================================

class AnomalyEventResponse(BaseModel):
    """Response model for anomaly event"""
    id: str
    instrument: str
    asset_class: str
    exchange: Optional[str]
    anomaly_type: str
    severity: str
    detected_at: datetime
    description: str
    z_score: Optional[float]
    price: Optional[float]
    volume: Optional[float]
    affected_instruments: Optional[List[str]]
    
    class Config:
        from_attributes = True


class AnomalyEventDetailResponse(BaseModel):
    """Response model for anomaly event with full raw data"""
    id: str
    instrument: str
    asset_class: str
    exchange: Optional[str]
    anomaly_type: str
    severity: str
    detected_at: datetime
    description: str
    z_score: Optional[float]
    price: Optional[float]
    volume: Optional[float]
    affected_instruments: Optional[List[str]]
    raw_data: Optional[dict]
    
    class Config:
        from_attributes = True


class AnomalyEventsResponse(BaseModel):
    """Paginated response for anomaly events"""
    events: List[AnomalyEventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DeliveryLogEntry(BaseModel):
    """Response model for delivery log entry"""
    id: str
    anomaly_event_id: str
    alert_rule_id: str
    channel: str
    status: str
    attempt_number: int
    delivered_at: Optional[datetime]
    error_message: Optional[str]
    detection_to_delivery_ms: Optional[int]
    created_at: datetime
    
    # Event details (joined)
    instrument: Optional[str]
    anomaly_type: Optional[str]
    severity: Optional[str]
    description: Optional[str]
    
    class Config:
        from_attributes = True


class DeliveryLogResponse(BaseModel):
    """Paginated response for delivery log"""
    logs: List[DeliveryLogEntry]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_watchlist_instruments(user_id: str, session: AsyncSession) -> List[str]:
    """
    Get list of instruments in user's watchlist
    
    TODO: Implement proper watchlist lookup from user service
    For now, returns all instruments (no filtering)
    
    Args:
        user_id: User ID
        session: Database session
        
    Returns:
        List of instrument symbols
    """
    # Placeholder - in production, this would query the user's watchlist
    # For now, return None to indicate "all instruments"
    return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/events", response_model=AnomalyEventsResponse)
async def get_anomaly_events(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    instrument: Optional[str] = Query(None, description="Filter by instrument symbol"),
    asset_class: Optional[str] = Query(None, description="Filter by asset class"),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO format)"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Get paginated anomaly events visible to user (based on their watchlist instruments)
    
    **Filters:**
    - instrument: Filter by specific instrument symbol
    - asset_class: Filter by asset class (equity, fo, crypto, forex, commodity)
    - anomaly_type: Filter by anomaly type (price_spike, volume_surge, etc.)
    - severity: Filter by severity (low, medium, high, critical)
    - start_date: Filter events after this date
    - end_date: Filter events before this date
    
    **Pagination:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    
    **Returns:**
    Paginated list of anomaly events with summary information
    
    **Task 43 Sub-task 1**: GET /api/v1/alerts/events
    """
    try:
        # Get user's watchlist instruments
        watchlist_instruments = await get_user_watchlist_instruments(user_id, session)
        
        # Build query filters
        filters = []
        
        # Filter by watchlist (if available)
        if watchlist_instruments is not None:
            filters.append(AnomalyEvent.instrument.in_(watchlist_instruments))
        
        # Apply user-provided filters
        if instrument:
            filters.append(AnomalyEvent.instrument == instrument)
        
        if asset_class:
            filters.append(AnomalyEvent.asset_class == asset_class)
        
        if anomaly_type:
            try:
                anomaly_type_enum = AnomalyType[anomaly_type.upper()]
                filters.append(AnomalyEvent.anomaly_type == anomaly_type_enum)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid anomaly_type: {anomaly_type}"
                )
        
        if severity:
            try:
                severity_enum = AnomalySeverity[severity.upper()]
                filters.append(AnomalyEvent.severity == severity_enum)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid severity: {severity}"
                )
        
        if start_date:
            filters.append(AnomalyEvent.detected_at >= start_date)
        
        if end_date:
            filters.append(AnomalyEvent.detected_at <= end_date)
        
        # Count total matching events
        count_query = select(func.count()).select_from(AnomalyEvent)
        if filters:
            count_query = count_query.where(and_(*filters))
        
        result = await session.execute(count_query)
        total = result.scalar()
        
        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        
        # Query events with pagination
        query = select(AnomalyEvent)
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(desc(AnomalyEvent.detected_at)).offset(offset).limit(page_size)
        
        result = await session.execute(query)
        events = result.scalars().all()
        
        # Convert to response models
        event_responses = [
            AnomalyEventResponse(
                id=str(event.id),
                instrument=event.instrument,
                asset_class=event.asset_class,
                exchange=event.exchange,
                anomaly_type=event.anomaly_type.value,
                severity=event.severity.value,
                detected_at=event.detected_at,
                description=event.description,
                z_score=event.z_score,
                price=event.price,
                volume=event.volume,
                affected_instruments=event.affected_instruments,
            )
            for event in events
        ]
        
        return AnomalyEventsResponse(
            events=event_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error fetching anomaly events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch anomaly events: {str(e)}"
        )


@router.get("/events/{event_id}", response_model=AnomalyEventDetailResponse)
async def get_anomaly_event_detail(
    event_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Get full event detail with all raw_data
    
    **Parameters:**
    - event_id: UUID of the anomaly event
    
    **Returns:**
    Complete anomaly event details including raw_data field
    
    **Task 43 Sub-task 2**: GET /api/v1/alerts/events/{id}
    """
    try:
        # Parse UUID
        try:
            event_uuid = uuid.UUID(event_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event_id format: {event_id}"
            )
        
        # Query event
        query = select(AnomalyEvent).where(AnomalyEvent.id == event_uuid)
        result = await session.execute(query)
        event = result.scalar_one_or_none()
        
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Anomaly event not found: {event_id}"
            )
        
        # Check if user has access to this event (based on watchlist)
        watchlist_instruments = await get_user_watchlist_instruments(user_id, session)
        if watchlist_instruments is not None and event.instrument not in watchlist_instruments:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this event"
            )
        
        # Convert to response model
        return AnomalyEventDetailResponse(
            id=str(event.id),
            instrument=event.instrument,
            asset_class=event.asset_class,
            exchange=event.exchange,
            anomaly_type=event.anomaly_type.value,
            severity=event.severity.value,
            detected_at=event.detected_at,
            description=event.description,
            z_score=event.z_score,
            price=event.price,
            volume=event.volume,
            affected_instruments=event.affected_instruments,
            raw_data=event.raw_data,
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error fetching anomaly event detail: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch anomaly event detail: {str(e)}"
        )


@router.get("/delivery-log", response_model=DeliveryLogResponse)
async def get_delivery_log(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    channel: Optional[str] = Query(None, description="Filter by delivery channel"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by delivery status"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO format)"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Get user's delivery log showing what was sent and to which channels
    
    **Filters:**
    - channel: Filter by delivery channel (in_app, push, email, sms, whatsapp, telegram, webhook)
    - status: Filter by delivery status (pending, sent, failed, skipped)
    - start_date: Filter logs after this date
    - end_date: Filter logs before this date
    
    **Pagination:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    
    **Returns:**
    Paginated list of delivery log entries with event details
    
    **Task 43 Sub-task 3**: GET /api/v1/alerts/delivery-log
    """
    try:
        # Parse user_id as UUID
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid user_id format: {user_id}"
            )
        
        # Build query filters
        filters = [AlertDeliveryLog.user_id == user_uuid]
        
        if channel:
            filters.append(AlertDeliveryLog.channel == channel)
        
        if status_filter:
            filters.append(AlertDeliveryLog.status == status_filter)
        
        if start_date:
            filters.append(AlertDeliveryLog.created_at >= start_date)
        
        if end_date:
            filters.append(AlertDeliveryLog.created_at <= end_date)
        
        # Count total matching logs
        count_query = select(func.count()).select_from(AlertDeliveryLog)
        if filters:
            count_query = count_query.where(and_(*filters))
        
        result = await session.execute(count_query)
        total = result.scalar()
        
        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        
        # Query logs with pagination and join with events
        query = (
            select(AlertDeliveryLog, AnomalyEvent)
            .join(AnomalyEvent, AlertDeliveryLog.anomaly_event_id == AnomalyEvent.id)
        )
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(desc(AlertDeliveryLog.created_at)).offset(offset).limit(page_size)
        
        result = await session.execute(query)
        rows = result.all()
        
        # Convert to response models
        log_responses = [
            DeliveryLogEntry(
                id=str(log.id),
                anomaly_event_id=str(log.anomaly_event_id),
                alert_rule_id=str(log.alert_rule_id),
                channel=log.channel,
                status=log.status,
                attempt_number=log.attempt_number,
                delivered_at=log.delivered_at,
                error_message=log.error_message,
                detection_to_delivery_ms=log.detection_to_delivery_ms,
                created_at=log.created_at,
                # Event details
                instrument=event.instrument,
                anomaly_type=event.anomaly_type.value,
                severity=event.severity.value,
                description=event.description,
            )
            for log, event in rows
        ]
        
        return DeliveryLogResponse(
            logs=log_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error fetching delivery log: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch delivery log: {str(e)}"
        )


@router.delete("/events/{event_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_anomaly_event(
    event_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Dismiss (delete) an anomaly event from the database upon user dismissal.
    """
    try:
        # Parse event_id as UUID
        try:
            event_uuid = uuid.UUID(event_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event_id format: {event_id}"
            )
        
        # Query event
        query = select(AnomalyEvent).where(AnomalyEvent.id == event_uuid)
        result = await session.execute(query)
        event = result.scalar_one_or_none()
        
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Anomaly event not found: {event_id}"
            )
            
        # Delete from database
        await session.delete(event)
        await session.commit()
        
        logger.info(f"Anomaly event {event_id} dismissed (deleted from DB) by user {user_id}")
        return {"success": True, "message": f"Event '{event_id}' dismissed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing anomaly event: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dismiss event: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for alert history API
    
    Returns:
        dict with service status
    """
    return {
        "status": "healthy",
        "service": "alert_history_api",
        "timestamp": datetime.utcnow().isoformat(),
    }
