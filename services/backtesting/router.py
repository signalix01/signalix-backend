"""
FastAPI router for backtesting endpoints.

Implements:
- POST /api/v1/backtest/run: Submit backtest with tier-based concurrent limits
- GET /api/v1/backtest/{task_id}/status: Check backtest status
- GET /api/v1/backtest/{task_id}/result: Retrieve complete result
- GET /api/v1/backtest/history: Paginated user history

Requirements: 4.1, 4.2, 16.5, 16.6
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid
import logging
from services.backtesting.models import BacktestConfig, BacktestResult
from services.backtesting.tasks import run_backtest_task
from services.backtesting.db_client import get_db_client
from services.backtesting.redis_client import get_redis_client
from celery.result import AsyncResult
from services.backtesting.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtesting"])


class BacktestSubmitResponse(BaseModel):
    """Response from backtest submission"""
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Initial status (pending)")
    message: str = Field(..., description="Success message")


class BacktestStatusResponse(BaseModel):
    """Response from status check"""
    task_id: str
    status: str = Field(..., description="pending/running/complete/failed")
    progress: int = Field(..., description="Progress percentage (0-100)")
    submitted_at: str
    backtest_id: Optional[str] = None
    error: Optional[str] = None


class BacktestHistoryItem(BaseModel):
    """Single item in backtest history"""
    task_id: str
    backtest_id: Optional[str]
    instrument: str
    strategy_name: str
    mode: str
    status: str
    submitted_at: str
    total_return_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None


class BacktestHistoryResponse(BaseModel):
    """Response from history endpoint"""
    total: int
    page: int
    limit: int
    items: List[BacktestHistoryItem]


# Helper function to extract user_id from auth header
# In production, this would use proper JWT authentication
async def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract user ID from authorization header.
    
    In production, this would validate JWT and extract user_id.
    For now, returns a test user ID.
    """
    # TODO: Implement proper JWT authentication
    # For now, return test user or extract from header
    if authorization and authorization.startswith("Bearer "):
        # In production: decode JWT and extract user_id
        return "test-user-id"
    return "test-user-id"


# Helper function to get user tier
# In production, this would query the user's subscription tier from database
async def get_user_tier(user_id: str) -> str:
    """
    Get user's subscription tier.
    
    In production, this would query the database.
    For now, returns 'free' tier.
    """
    # TODO: Query user tier from database
    # For now, return free tier
    return "free"


@router.post("/run", response_model=BacktestSubmitResponse)
async def run_backtest(
    config: BacktestConfig,
    user_id: str = Depends(get_current_user_id)
):
    """
    Submit a backtest for execution.
    
    The backtest runs asynchronously via Celery. Use the returned task_id to poll status
    and retrieve results when complete.
    
    Implements tier-based concurrent backtest limits (Req 16.6):
    - Free tier: 1 concurrent backtest
    - Equity tier: 2 concurrent backtests
    - F&O tier: 3 concurrent backtests
    - Pro tier: 5 concurrent backtests
    - Enterprise: unlimited
    
    Args:
        config: Complete backtest configuration
        user_id: User identifier (from auth header)
        
    Returns:
        BacktestSubmitResponse with task_id
        
    Raises:
        HTTPException: If validation fails, concurrent limit reached, or submission error
    """
    try:
        # Validate config
        if not config.strategy_spec:
            raise HTTPException(status_code=422, detail="strategy_spec is required")
        
        if not config.instrument:
            raise HTTPException(status_code=422, detail="instrument is required")
        
        # Get user tier
        user_tier = await get_user_tier(user_id)
        
        # Check concurrent backtest limit (Req 16.6)
        redis_client = await get_redis_client()
        can_start = await redis_client.can_start_backtest(user_id, user_tier)
        
        if not can_start:
            current_count = await redis_client.get_concurrent_count(user_id)
            limit = redis_client.TIER_LIMITS.get(user_tier.lower(), 1)
            raise HTTPException(
                status_code=429,
                detail=f"Concurrent backtest limit reached for {user_tier} tier: "
                       f"{current_count}/{limit} running. Please wait for a backtest to complete."
            )
        
        # Generate backtest ID
        backtest_id = str(uuid.uuid4())
        
        # Create pending database record
        db_client = get_db_client()
        db_client.create_pending_backtest(backtest_id, config, user_id)
        
        # Increment concurrent count
        await redis_client.increment_concurrent_count(user_id)
        
        # Submit Celery task
        task = run_backtest_task.apply_async(
            args=[config.json(), backtest_id, user_id],
            task_id=backtest_id  # Use backtest_id as task_id for consistency
        )
        
        logger.info(
            f"Submitted backtest {backtest_id} for user {user_id} ({user_tier} tier)"
        )
        
        return BacktestSubmitResponse(
            task_id=backtest_id,
            status="pending",
            message=f"Backtest submitted successfully. Use task_id to check status."
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit backtest: {str(e)}")


@router.get("/{task_id}/status", response_model=BacktestStatusResponse)
async def get_backtest_status(
    task_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get backtest task status.
    
    Returns current status and progress percentage.
    
    Args:
        task_id: Task identifier from submission
        user_id: User identifier (from auth header)
        
    Returns:
        BacktestStatusResponse with current status and progress
        
    Raises:
        HTTPException: If task_id not found or access denied
    """
    try:
        # Get status from database
        db_client = get_db_client()
        db_status = db_client.get_backtest_status(task_id)
        
        if not db_status:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Get Celery task status for progress
        celery_task = AsyncResult(task_id, app=celery_app)
        
        progress = 0
        if celery_task.state == 'PENDING':
            progress = 0
        elif celery_task.state == 'PROGRESS':
            progress = celery_task.info.get('progress', 0) if celery_task.info else 0
        elif celery_task.state == 'SUCCESS':
            progress = 100
        elif celery_task.state == 'FAILURE':
            progress = 0
        
        return BacktestStatusResponse(
            task_id=task_id,
            status=db_status['status'],
            progress=progress,
            submitted_at=db_status['created_at'],
            backtest_id=task_id,
            error=db_status.get('error_message')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backtest status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/{task_id}/result", response_model=BacktestResult)
async def get_backtest_result(
    task_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get backtest result.
    
    Only available when task status is 'complete'.
    
    Args:
        task_id: Task identifier from submission
        user_id: User identifier (from auth header)
        
    Returns:
        Complete BacktestResult
        
    Raises:
        HTTPException: If task not found, not complete, or access denied
    """
    try:
        # Get status first
        db_client = get_db_client()
        db_status = db_client.get_backtest_status(task_id)
        
        if not db_status:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        if db_status['status'] != 'complete':
            raise HTTPException(
                status_code=400,
                detail=f"Task is {db_status['status']}, result not available yet"
            )
        
        # Get result
        result = db_client.get_backtest_result(task_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        
        # Decrement concurrent count when result is retrieved
        # (User has acknowledged completion)
        redis_client = await get_redis_client()
        await redis_client.decrement_concurrent_count(user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backtest result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get result: {str(e)}")


@router.get("/history", response_model=BacktestHistoryResponse)
async def get_backtest_history(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get backtest history for current user.
    
    Returns paginated list of past backtests sorted by submission time (newest first).
    
    Args:
        page: Page number (1-indexed)
        limit: Items per page (max 100)
        status: Optional status filter (pending/running/complete/failed)
        user_id: User identifier (from auth header)
        
    Returns:
        BacktestHistoryResponse with paginated items
    """
    try:
        db_client = get_db_client()
        
        # Get user's backtest history from database
        results, total = db_client.get_user_backtest_history(
            user_id=user_id,
            page=page,
            limit=limit,
            status_filter=status
        )
        
        # Build response items
        items = []
        for record in results:
            # Get strategy name from result_data if available
            strategy_name = "Unknown Strategy"
            if record.result_data and 'strategy_id' in record.result_data:
                strategy_name = record.result_data.get('strategy_id', strategy_name)
            
            item = BacktestHistoryItem(
                task_id=str(record.id),
                backtest_id=str(record.id),
                instrument=record.instrument,
                strategy_name=strategy_name,
                mode=record.mode,
                status=record.status,
                submitted_at=record.created_at.isoformat(),
                total_return_pct=record.total_return_pct,
                sharpe_ratio=record.sharpe_ratio
            )
            items.append(item)
        
        return BacktestHistoryResponse(
            total=total,
            page=page,
            limit=limit,
            items=items
        )
        
    except Exception as e:
        logger.error(f"Failed to get backtest history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "backtesting",
        "version": "1.0.0"
    }
