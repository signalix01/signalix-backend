"""
Analytics Router

Exposes retention metrics and analytics endpoints.

Requirements: 10.9
Task: 23
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.services.retention_service import retention_service

logger = logging.getLogger(__name__)

router = APIRouter()


class RetentionMetric(BaseModel):
    """Retention metric model"""
    cohort_date: str
    retention_day: int
    cohort_size: int
    retained_users: int
    retention_rate: float
    activated_cohort_size: int
    activated_retained_users: int
    activated_retention_rate: float
    non_activated_cohort_size: int
    non_activated_retained_users: int
    non_activated_retention_rate: float
    computed_at: Optional[str] = None


class RetentionSummary(BaseModel):
    """Retention summary model"""
    total_cohorts: int
    total_users: int
    avg_day1_retention: float
    avg_day7_retention: float
    avg_day30_retention: float


class RetentionResponse(BaseModel):
    """Response model for retention endpoint"""
    metrics: List[RetentionMetric]
    summary: RetentionSummary
    total_metrics: int


class RecordSessionRequest(BaseModel):
    """Request model for recording user session"""
    user_id: str
    session_time: str = Field(..., description="ISO format timestamp")


class RecordSignupRequest(BaseModel):
    """Request model for recording user signup"""
    user_id: str
    signup_time: str = Field(..., description="ISO format timestamp")
    is_activated: bool = False


class UpdateActivationRequest(BaseModel):
    """Request model for updating activation status"""
    user_id: str
    is_activated: bool


@router.get("/retention", response_model=RetentionResponse)
async def get_retention_metrics(
    cohort_date: Optional[str] = Query(None, description="Filter by cohort date (YYYY-MM-DD)"),
    retention_day: Optional[int] = Query(None, description="Filter by retention day (1, 7, or 30)"),
    start_date: Optional[str] = Query(None, description="Filter cohorts from this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter cohorts up to this date (YYYY-MM-DD)")
):
    """
    Get retention metrics
    
    Returns Day 1, Day 7, Day 30 cohort retention rates.
    Supports filtering by cohort date, retention day, and date range.
    Includes retention breakdown by activation status.
    """
    try:
        # Validate retention_day if provided
        if retention_day is not None and retention_day not in [1, 7, 30]:
            raise HTTPException(
                status_code=400,
                detail="retention_day must be 1, 7, or 30"
            )
        
        # Get metrics
        metrics = retention_service.get_retention_metrics(
            cohort_date=cohort_date,
            retention_day=retention_day,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get summary
        summary = retention_service.get_retention_summary()
        
        return RetentionResponse(
            metrics=[RetentionMetric(**m) for m in metrics],
            summary=RetentionSummary(**summary),
            total_metrics=len(metrics)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting retention metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get retention metrics: {str(e)}"
        )


@router.get("/retention/summary", response_model=RetentionSummary)
async def get_retention_summary():
    """
    Get retention summary
    
    Returns summary statistics for retention metrics.
    """
    try:
        summary = retention_service.get_retention_summary()
        return RetentionSummary(**summary)
        
    except Exception as e:
        logger.error(f"Error getting retention summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get retention summary: {str(e)}"
        )


@router.post("/retention/compute")
async def compute_retention_metrics():
    """
    Manually trigger retention computation
    
    Computes retention metrics for all cohorts and stores results.
    This is normally run as a daily cron job.
    """
    try:
        result = retention_service.run_daily_retention_computation()
        
        return {
            "success": True,
            "message": "Retention metrics computed successfully",
            **result
        }
        
    except Exception as e:
        logger.error(f"Error computing retention metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute retention metrics: {str(e)}"
        )


@router.post("/sessions/record")
async def record_user_session(request: RecordSessionRequest):
    """
    Record a user session
    
    Used to track user activity for retention calculation.
    """
    try:
        # Parse timestamp
        try:
            session_time = datetime.fromisoformat(request.session_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid session_time format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)"
            )
        
        # Record session
        retention_service.record_user_session(request.user_id, session_time)
        
        return {
            "success": True,
            "message": "User session recorded",
            "user_id": request.user_id,
            "session_time": session_time.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording user session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record user session: {str(e)}"
        )


@router.post("/signups/record")
async def record_user_signup(request: RecordSignupRequest):
    """
    Record a user signup
    
    Used to track cohort membership for retention calculation.
    """
    try:
        # Parse timestamp
        try:
            signup_time = datetime.fromisoformat(request.signup_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid signup_time format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)"
            )
        
        # Record signup
        retention_service.record_user_signup(
            request.user_id,
            signup_time,
            request.is_activated
        )
        
        return {
            "success": True,
            "message": "User signup recorded",
            "user_id": request.user_id,
            "signup_time": signup_time.isoformat(),
            "is_activated": request.is_activated
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording user signup: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record user signup: {str(e)}"
        )


@router.put("/activation/update")
async def update_activation_status(request: UpdateActivationRequest):
    """
    Update user activation status
    
    Used to track retention by activation status.
    """
    try:
        retention_service.update_activation_status(
            request.user_id,
            request.is_activated
        )
        
        return {
            "success": True,
            "message": "Activation status updated",
            "user_id": request.user_id,
            "is_activated": request.is_activated
        }
        
    except Exception as e:
        logger.error(f"Error updating activation status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update activation status: {str(e)}"
        )


@router.get("/retention/cohort/{cohort_date}")
async def get_cohort_retention(cohort_date: str):
    """
    Get retention metrics for a specific cohort
    
    Returns Day 1, Day 7, Day 30 retention for the specified cohort.
    """
    try:
        metrics = retention_service.get_retention_metrics(cohort_date=cohort_date)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"No retention metrics found for cohort {cohort_date}"
            )
        
        return {
            "cohort_date": cohort_date,
            "metrics": metrics,
            "total_metrics": len(metrics)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cohort retention: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cohort retention: {str(e)}"
        )
