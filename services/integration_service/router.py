"""
Integration Service Router

FastAPI router for webhook processing and integration management.
Requirements: 1.1, 1.6, 2.1, 3.1, 17.1, 17.7
"""

import os
import uuid
import json
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request, Header, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, UUID4, validator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete as sql_delete, and_, desc, func
from sqlalchemy.orm import selectinload
import redis.asyncio as redis

from services.integration_service.models.webhook_models import (
    WebhookConfig, Signal, WebhookLog, DeadLetterWebhook,
    IntegrationType, SignalAction, SignalStatus, WebhookStatus
)
from services.integration_service.handlers.webhook_handler import WebhookHandler, ValidationResult
from services.integration_service.handlers.rate_limiter import RateLimiter
from services.integration_service.parsers.tradingview_parser import TradingViewParser, ParsedSignal
from services.integration_service.parsers.amibroker_parser import AmibrokerParser, AFLParameters
from services.integration_service.parsers.chartink_parser import ChartInkParser, ChartInkAlert
from services.integration_service.queue.webhook_queue import WebhookQueue, WebhookJob, QueuePriority
from services.integration_service.queue.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integration", tags=["integration"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis client initialized")
except Exception as e:
    logger.warning(f"Redis not available: {str(e)}")

# Initialize components
webhook_handler = WebhookHandler()
rate_limiter = RateLimiter(redis_client)
tradingview_parser = TradingViewParser()
amibroker_parser = AmibrokerParser()
chartink_parser = ChartInkParser()
webhook_queue = WebhookQueue(redis_client)

# Circuit breaker for signal forwarding
circuit_breaker_config = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=60,
    half_open_max_calls=3,
    success_threshold=2
)

# ============================================================================
# Dependencies
# ============================================================================

async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user_id() -> str:
    """
    Get current authenticated user ID from JWT token
    
    TODO: Implement proper JWT authentication middleware
    For now, returns a test user ID
    """
    return "00000000-0000-0000-0000-000000000001"


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateWebhookConfigRequest(BaseModel):
    """Request to create webhook configuration"""
    integration_type: IntegrationType
    rate_limit_per_minute: int = Field(default=100, ge=1, le=1000)
    send_confirmation: bool = True


class WebhookConfigResponse(BaseModel):
    """Webhook configuration response"""
    id: str
    integration_type: str
    webhook_url: str
    enabled: bool
    rate_limit_per_minute: int
    send_confirmation: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True


class WebhookConfigListResponse(BaseModel):
    """List of webhook configurations"""
    configs: List[WebhookConfigResponse]
    total: int


class SignalResponse(BaseModel):
    """Signal response"""
    id: str
    integration_type: str
    symbol: str
    action: str
    quantity: int
    price: Optional[float]
    order_type: str
    product_type: str
    status: str
    received_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SignalListResponse(BaseModel):
    """List of signals"""
    signals: List[SignalResponse]
    total: int


class WebhookLogResponse(BaseModel):
    """Webhook log response"""
    id: str
    integration_type: str
    status: str
    signature_valid: Optional[bool]
    timestamp_valid: Optional[bool]
    rate_limit_exceeded: bool
    error_message: Optional[str]
    processing_time_ms: Optional[int]
    source_ip: Optional[str]
    received_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class QueueMetricsResponse(BaseModel):
    """Queue metrics response"""
    queue_depth: Dict[str, int]
    processing_count: int
    dead_letter_count: int
    metrics: Dict[str, int]


class IntegrationMetricsResponse(BaseModel):
    """Integration service metrics"""
    total_webhooks_received: int
    total_webhooks_processed: int
    total_webhooks_failed: int
    success_rate: float
    average_latency_ms: float
    queue_metrics: QueueMetricsResponse


class RegenerateSecretResponse(BaseModel):
    """Regenerate webhook secret response"""
    secret_key: str
    webhook_url: str


# ============================================================================
# Webhook Endpoints
# ============================================================================

@router.post(
    "/webhook/{integration_type}/{webhook_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive webhook from external platform",
    description="""
    Webhook endpoint for TradingView, Amibroker, and ChartInk.
    
    - Validates webhook signature using HMAC-SHA256
    - Checks rate limits
    - Queues webhook for processing
    - Returns 202 Accepted immediately
    
    Requirements: 1.1, 17.1, 17.2, 17.4, 17.5, 17.6
    """
)
async def receive_webhook(
    integration_type: IntegrationType,
    webhook_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: Optional[str] = Header(None),
    x_timestamp: Optional[str] = Header(None),
    x_webhook_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Receive and queue webhook from external platforms
    
    Args:
        integration_type: Type of integration (tradingview, amibroker, chartink)
        webhook_id: Unique webhook identifier (user_id or config_id)
        request: FastAPI request object
        x_signature: Webhook signature header
        x_timestamp: Timestamp header for replay protection
        x_webhook_signature: Alternative signature header
        db: Database session
        
    Returns:
        202 Accepted if webhook is queued successfully
    """
    start_time = datetime.utcnow()
    source_ip = request.client.host if request.client else "unknown"
    
    try:
        # Get raw payload
        body = await request.body()
        payload = json.loads(body.decode('utf-8'))
        
        # Find webhook configuration
        config_result = await db.execute(
            select(WebhookConfig).where(
                and_(
                    WebhookConfig.webhook_url.contains(webhook_id),
                    WebhookConfig.integration_type == integration_type,
                    WebhookConfig.enabled == True
                )
            )
        )
        config = config_result.scalar_one_or_none()
        
        if not config:
            logger.warning(f"Webhook config not found: {webhook_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook configuration not found or disabled"
            )
        
        # Determine signature
        signature = x_signature or x_webhook_signature
        
        # Extract timestamp
        timestamp = None
        if x_timestamp:
            try:
                timestamp = int(x_timestamp)
                if timestamp > 1_000_000_000_000:
                    timestamp = timestamp // 1000
            except ValueError:
                timestamp = None
        
        # Validate webhook
        validation = webhook_handler.validate_webhook(
            payload=body,
            signature=signature,
            secret=config.secret_key,
            timestamp=timestamp
        )
        
        # Check rate limit
        rate_allowed, rate_info = await rate_limiter.check_user_limit(
            user_id=str(config.user_id),
            integration_type=integration_type.value,
            custom_limit=config.rate_limit_per_minute
        )
        
        # Create log entry
        log = WebhookLog(
            id=uuid.uuid4(),
            user_id=config.user_id,
            integration_type=integration_type,
            config_id=config.id,
            payload=validation.sanitized_payload or payload,
            headers=dict(request.headers) if request.headers else {},
            signature=signature or "",
            signature_valid=validation.signature_valid,
            timestamp=datetime.utcfromtimestamp(timestamp) if timestamp else None,
            timestamp_valid=validation.timestamp_valid,
            status=WebhookStatus.RECEIVED,
            rate_limit_checked=True,
            rate_limit_exceeded=not rate_allowed,
            error_message=validation.error_message,
            source_ip=source_ip,
            received_at=start_time
        )
        
        db.add(log)
        await db.commit()
        
        # Update config last_used_at
        config.last_used_at = datetime.utcnow()
        await db.commit()
        
        # If validation failed or rate limited, return error
        if not validation.valid:
            log.status = WebhookStatus.FAILED
            log.processed_at = datetime.utcnow()
            log.processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=validation.error_message or "Invalid webhook"
            )
        
        if not rate_allowed:
            log.status = WebhookStatus.FAILED
            log.processed_at = datetime.utcnow()
            log.error_message = "Rate limit exceeded"
            log.processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(rate_info.get("reset_time", 60))}
            )
        
        # Update log status
        log.status = WebhookStatus.QUEUED
        log.validated_at = datetime.utcnow()
        log.queued_at = datetime.utcnow()
        await db.commit()
        
        # Create queue job
        job = WebhookJob(
            id=str(log.id),
            user_id=str(config.user_id),
            integration_type=integration_type.value,
            payload=validation.sanitized_payload or payload,
            headers=dict(request.headers),
            source_ip=source_ip,
            priority=QueuePriority.NORMAL,
            created_at=datetime.utcnow(),
            webhook_config_id=str(config.id),
            log_id=str(log.id)
        )
        
        # Queue for processing
        success = await webhook_queue.enqueue(job)
        
        if not success:
            log.status = WebhookStatus.FAILED
            log.error_message = "Failed to queue webhook"
            await db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue webhook"
            )
        
        # Process in background
        background_tasks.add_task(
            process_webhook_job,
            job,
            str(config.user_id),
            str(config.id)
        )
        
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Webhook accepted",
                "log_id": str(log.id),
                "queued": True
            }
        )
        
    except HTTPException:
        raise
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.exception("Webhook processing error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error"
        )


async def process_webhook_job(job: WebhookJob, user_id: str, config_id: str):
    """
    Process webhook job from queue
    
    This runs in the background to parse signals and forward to execution engine.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get log entry
            log_result = await db.execute(
                select(WebhookLog).where(WebhookLog.id == uuid.UUID(job.log_id))
            )
            log = log_result.scalar_one_or_none()
            
            if not log:
                logger.error(f"Log not found: {job.log_id}")
                return
            
            log.status = WebhookStatus.PROCESSING
            await db.commit()
            
            # Parse signal based on integration type
            signal_data = None
            
            if job.integration_type == "tradingview":
                signal_data = await parse_tradingview_signal(job.payload, user_id)
            elif job.integration_type == "amibroker":
                signal_data = await parse_amibroker_signal(job.payload, user_id)
            elif job.integration_type == "chartink":
                signal_data = await parse_chartink_signal(job.payload, user_id)
            
            if signal_data:
                # Create signal record
                signal = Signal(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    integration_type=IntegrationType(job.integration_type),
                    symbol=signal_data["symbol"],
                    action=SignalAction(signal_data["action"]),
                    quantity=signal_data.get("quantity", 1),
                    price=signal_data.get("price"),
                    order_type=signal_data.get("order_type", "MARKET"),
                    product_type=signal_data.get("product_type", "INTRADAY"),
                    parameters=signal_data.get("parameters", {}),
                    status=SignalStatus.FORWARDED,
                    received_at=job.created_at,
                    processed_at=datetime.utcnow(),
                    webhook_log_id=uuid.UUID(job.log_id) if job.log_id else None
                )
                
                db.add(signal)
                await db.commit()
                
                # Forward to execution engine
                await forward_signal_to_execution_engine(signal)
                
                # Update log
                log.status = WebhookStatus.PROCESSED
                log.processed_at = datetime.utcnow()
                log.processing_time_ms = int(
                    (datetime.utcnow() - log.received_at).total_seconds() * 1000
                )
                await db.commit()
                
                # Mark queue job as completed
                await webhook_queue.mark_completed(job.id)
                
                logger.info(f"Signal {signal.id} processed successfully")
            else:
                # Failed to parse signal
                log.status = WebhookStatus.FAILED
                log.error_message = "Failed to parse signal from payload"
                log.processed_at = datetime.utcnow()
                await db.commit()
                
                await webhook_queue.mark_failed(job, "Signal parsing failed")
                
    except Exception as e:
        logger.exception(f"Error processing webhook job {job.id}")
        
        # Mark as failed for retry
        try:
            await webhook_queue.mark_failed(job, str(e))
        except Exception:
            pass


async def parse_tradingview_signal(payload: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
    """Parse TradingView alert into signal format"""
    parsed = tradingview_parser.parse_alert(payload)
    
    if not parsed:
        return None
    
    return {
        "user_id": user_id,
        "integration_type": "tradingview",
        "symbol": parsed.symbol,
        "action": parsed.action.value,
        "quantity": parsed.quantity,
        "price": parsed.price,
        "order_type": parsed.order_type,
        "product_type": parsed.product_type,
        "parameters": parsed.parameters
    }


async def parse_amibroker_signal(payload: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
    """Parse Amibroker signal into signal format"""
    parsed = amibroker_parser.parse_signal(payload)
    
    if not parsed:
        return None
    
    return {
        "user_id": user_id,
        "integration_type": "amibroker",
        "symbol": parsed.symbol,
        "action": parsed.action.value,
        "quantity": parsed.quantity,
        "price": parsed.price,
        "order_type": parsed.order_type,
        "product_type": parsed.product_type,
        "parameters": {
            "time_frame": parsed.time_frame,
            "strategy_name": parsed.strategy_name,
            **parsed.custom_fields
        }
    }


async def parse_chartink_signal(payload: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
    """Parse ChartInk alert into signal format"""
    alert = chartink_parser.parse_alert(payload)
    
    if not alert or not alert.symbols:
        return None
    
    # For ChartInk, we take the first symbol for now
    # In a full implementation, you might want to create multiple signals
    symbol = alert.symbols[0]
    
    return {
        "user_id": user_id,
        "integration_type": "chartink",
        "symbol": symbol.symbol,
        "action": "buy",  # Default action for scanner alerts
        "quantity": 1,
        "price": symbol.price,
        "order_type": "MARKET",
        "product_type": "INTRADAY",
        "parameters": {
            "scan_name": alert.scan_name,
            "scan_url": alert.scan_url,
            "exchange": symbol.exchange,
            "volume": symbol.volume,
            "change_percent": symbol.change_percent,
            "conditions": symbol.conditions
        }
    }


async def forward_signal_to_execution_engine(signal: Signal):
    """
    Forward signal to Strategy Execution Engine
    
    Requirements: 1.3, 1.7, 2.7
    """
    try:
        # This would integrate with your execution engine
        # For now, we just log it
        logger.info(
            f"Forwarding signal {signal.id} to execution engine: "
            f"{signal.action.value} {signal.symbol}"
        )
        
        # TODO: Implement actual execution engine integration
        # This would typically:
        # 1. Send to a message queue (Redis/RabbitMQ)
        # 2. Or make HTTP call to execution service
        # 3. Or publish to WebSocket
        
    except Exception as e:
        logger.error(f"Failed to forward signal {signal.id}: {str(e)}")
        raise


# ============================================================================
# Webhook Configuration Endpoints
# ============================================================================

@router.post(
    "/webhooks/config",
    response_model=WebhookConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create webhook configuration",
    description="Create a new webhook configuration for TradingView, Amibroker, or ChartInk"
)
async def create_webhook_config(
    request: CreateWebhookConfigRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create webhook configuration"""
    try:
        # Generate unique webhook URL
        webhook_token = hashlib.sha256(
            f"{user_id}:{request.integration_type.value}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        webhook_url = f"/webhook/{request.integration_type.value}/{webhook_token}"
        
        # Generate secret key
        secret_key = hashlib.sha256(
            f"{user_id}:{webhook_token}:{uuid.uuid4()}".encode()
        ).hexdigest()
        
        # Create config
        config = WebhookConfig(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            integration_type=request.integration_type,
            webhook_url=webhook_url,
            secret_key=secret_key,
            enabled=True,
            rate_limit_per_minute=request.rate_limit_per_minute,
            send_confirmation=request.send_confirmation
        )
        
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
        # Return config (with secret shown once)
        return WebhookConfigResponse(
            **config.to_dict(),
            secret_key=secret_key  # Only shown on creation
        )
        
    except Exception as e:
        logger.exception("Error creating webhook config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create webhook configuration"
        )


@router.get(
    "/webhooks/config",
    response_model=WebhookConfigListResponse,
    summary="List webhook configurations",
    description="Get all webhook configurations for the current user"
)
async def list_webhook_configs(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """List webhook configurations"""
    try:
        result = await db.execute(
            select(WebhookConfig)
            .where(WebhookConfig.user_id == uuid.UUID(user_id))
            .order_by(desc(WebhookConfig.created_at))
        )
        configs = result.scalars().all()
        
        return WebhookConfigListResponse(
            configs=[WebhookConfigResponse.from_orm(c) for c in configs],
            total=len(configs)
        )
        
    except Exception as e:
        logger.exception("Error listing webhook configs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list webhook configurations"
        )


@router.post(
    "/webhooks/config/{config_id}/regenerate",
    response_model=RegenerateSecretResponse,
    summary="Regenerate webhook secret",
    description="Generate a new secret key for the webhook"
)
async def regenerate_secret(
    config_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate webhook secret"""
    try:
        result = await db.execute(
            select(WebhookConfig).where(
                and_(
                    WebhookConfig.id == uuid.UUID(config_id),
                    WebhookConfig.user_id == uuid.UUID(user_id)
                )
            )
        )
        config = result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook configuration not found"
            )
        
        # Generate new secret
        new_secret = hashlib.sha256(
            f"{user_id}:{config_id}:{uuid.uuid4()}".encode()
        ).hexdigest()
        
        config.secret_key = new_secret
        config.updated_at = datetime.utcnow()
        await db.commit()
        
        return RegenerateSecretResponse(
            secret_key=new_secret,
            webhook_url=config.webhook_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error regenerating secret")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate secret"
        )


@router.delete(
    "/webhooks/config/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete webhook configuration",
    description="Delete a webhook configuration"
)
async def delete_webhook_config(
    config_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Delete webhook configuration"""
    try:
        result = await db.execute(
            select(WebhookConfig).where(
                and_(
                    WebhookConfig.id == uuid.UUID(config_id),
                    WebhookConfig.user_id == uuid.UUID(user_id)
                )
            )
        )
        config = result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook configuration not found"
            )
        
        await db.delete(config)
        await db.commit()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting webhook config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete webhook configuration"
        )


# ============================================================================
# Signal Management Endpoints
# ============================================================================

@router.get(
    "/signals",
    response_model=SignalListResponse,
    summary="List signals",
    description="Get all signals for the current user"
)
async def list_signals(
    integration_type: Optional[IntegrationType] = None,
    status: Optional[SignalStatus] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """List signals with optional filters"""
    try:
        query = select(Signal).where(Signal.user_id == uuid.UUID(user_id))
        
        if integration_type:
            query = query.where(Signal.integration_type == integration_type)
        
        if status:
            query = query.where(Signal.status == status)
        
        # Get total count
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar()
        
        # Get paginated results
        query = query.order_by(desc(Signal.received_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        signals = result.scalars().all()
        
        return SignalListResponse(
            signals=[SignalResponse.from_orm(s) for s in signals],
            total=total
        )
        
    except Exception as e:
        logger.exception("Error listing signals")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list signals"
        )


# ============================================================================
# Logs and Metrics Endpoints
# ============================================================================

@router.get(
    "/logs",
    response_model=List[WebhookLogResponse],
    summary="Get webhook logs",
    description="Get webhook processing logs"
)
async def get_webhook_logs(
    integration_type: Optional[IntegrationType] = None,
    status: Optional[WebhookStatus] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get webhook logs"""
    try:
        query = select(WebhookLog).where(WebhookLog.user_id == uuid.UUID(user_id))
        
        if integration_type:
            query = query.where(WebhookLog.integration_type == integration_type)
        
        if status:
            query = query.where(WebhookLog.status == status)
        
        query = query.order_by(desc(WebhookLog.received_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [WebhookLogResponse.from_orm(log) for log in logs]
        
    except Exception as e:
        logger.exception("Error getting webhook logs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get webhook logs"
        )


@router.get(
    "/metrics",
    response_model=IntegrationMetricsResponse,
    summary="Get integration metrics",
    description="Get integration service metrics and statistics"
)
async def get_metrics(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get integration service metrics"""
    try:
        # Get webhook counts
        total_result = await db.execute(
            select(func.count()).where(WebhookLog.user_id == uuid.UUID(user_id))
        )
        total_webhooks = total_result.scalar()
        
        processed_result = await db.execute(
            select(func.count()).where(
                and_(
                    WebhookLog.user_id == uuid.UUID(user_id),
                    WebhookLog.status == WebhookStatus.PROCESSED
                )
            )
        )
        processed_webhooks = processed_result.scalar()
        
        failed_result = await db.execute(
            select(func.count()).where(
                and_(
                    WebhookLog.user_id == uuid.UUID(user_id),
                    WebhookLog.status == WebhookStatus.FAILED
                )
            )
        )
        failed_webhooks = failed_result.scalar()
        
        # Calculate success rate
        success_rate = (
            (processed_webhooks / (processed_webhooks + failed_webhooks) * 100)
            if (processed_webhooks + failed_webhooks) > 0 else 100.0
        )
        
        # Get average latency
        latency_result = await db.execute(
            select(func.avg(WebhookLog.processing_time_ms)).where(
                and_(
                    WebhookLog.user_id == uuid.UUID(user_id),
                    WebhookLog.processing_time_ms.isnot(None)
                )
            )
        )
        avg_latency = latency_result.scalar() or 0
        
        # Get queue metrics
        queue_depth = await webhook_queue.get_queue_depth()
        processing_count = await webhook_queue.get_processing_count()
        dead_letter_count = await webhook_queue.get_dead_letter_count()
        queue_metrics_dict = await webhook_queue.get_metrics()
        
        return IntegrationMetricsResponse(
            total_webhooks_received=total_webhooks,
            total_webhooks_processed=processed_webhooks,
            total_webhooks_failed=failed_webhooks,
            success_rate=round(success_rate, 2),
            average_latency_ms=round(avg_latency, 2),
            queue_metrics=QueueMetricsResponse(
                queue_depth=queue_depth,
                processing_count=processing_count,
                dead_letter_count=dead_letter_count,
                metrics=queue_metrics_dict
            )
        )
        
    except Exception as e:
        logger.exception("Error getting metrics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get metrics"
        )


@router.get(
    "/dead-letter",
    summary="Get dead letter queue",
    description="Get failed webhooks from dead letter queue"
)
async def get_dead_letter_queue(
    limit: int = 100,
    user_id: str = Depends(get_current_user_id)
):
    """Get dead letter queue items"""
    try:
        jobs = await webhook_queue.get_dead_letter_jobs(limit)
        
        # Filter by user_id (simplified - in production, index by user)
        user_jobs = [
            job for job in jobs 
            if job.get("job", {}).get("user_id") == user_id
        ]
        
        return {
            "jobs": user_jobs,
            "total": len(user_jobs)
        }
        
    except Exception as e:
        logger.exception("Error getting dead letter queue")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dead letter queue"
        )


@router.post(
    "/dead-letter/{job_id}/replay",
    summary="Replay dead letter job",
    description="Replay a failed webhook from dead letter queue"
)
async def replay_dead_letter(
    job_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Replay a dead letter job"""
    try:
        success = await webhook_queue.replay_dead_letter_job(job_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found in dead letter queue"
            )
        
        return {"message": "Job replayed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error replaying dead letter job")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to replay job"
        )
