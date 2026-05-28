"""
Email Sequence Router
Handles enrollment and management of email sequences
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from rq import Queue
from redis import Redis

from app.config import settings
from app.data.sequences.onboarding import (
    get_onboarding_sequence,
    get_sequence_metadata as get_onboarding_metadata
)
from app.data.sequences.lead_magnet import (
    get_lead_magnet_sequence,
    get_sequence_metadata as get_lead_magnet_metadata
)
from app.tasks.email_tasks import redis_conn

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize email queue
email_queue = Queue('emails', connection=redis_conn)


# Request/Response Models

class EnrollSequenceRequest(BaseModel):
    """Request to enroll user in email sequence"""
    user_id: str
    email: EmailStr
    sequence_name: str
    context: Optional[Dict[str, Any]] = {}
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "sequence_name": "onboarding",
                "context": {
                    "first_name": "Rajesh",
                    "signup_date": "2024-01-15"
                }
            }
        }


class EnrollSequenceResponse(BaseModel):
    """Response after enrolling in sequence"""
    success: bool
    message: str
    sequence_name: str
    total_emails: int
    scheduled_jobs: int
    enrollment_id: Optional[str] = None


class SequenceStatusResponse(BaseModel):
    """Sequence enrollment status"""
    user_id: str
    email: str
    sequence_name: str
    enrolled_at: datetime
    emails_sent: int
    emails_remaining: int
    next_email_at: Optional[datetime] = None
    completed: bool


# Endpoints

@router.post("/enroll", response_model=EnrollSequenceResponse)
async def enroll_in_sequence(
    request: EnrollSequenceRequest,
    background_tasks: BackgroundTasks
) -> EnrollSequenceResponse:
    """
    Enroll a user in an email sequence
    
    Schedules all emails in the sequence with appropriate delays using rq's eta parameter.
    Currently supports 'onboarding' sequence (Day 0-7 welcome emails).
    
    Args:
        request: Enrollment request with user_id, email, sequence_name, and context
        
    Returns:
        EnrollSequenceResponse with enrollment details and scheduled job count
        
    Raises:
        HTTPException: If sequence not found or enrollment fails
    """
    try:
        # Validate sequence name and get appropriate sequence
        if request.sequence_name == "onboarding":
            sequence = get_onboarding_sequence()
        elif request.sequence_name == "lead_magnet":
            sequence = get_lead_magnet_sequence()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown sequence: {request.sequence_name}. Supported sequences: 'onboarding', 'lead_magnet'"
            )
        
        # Schedule all emails in the sequence
        scheduled_count = 0
        enrollment_time = datetime.utcnow()
        
        for step in sequence:
            # Calculate delivery time (eta)
            delivery_time = enrollment_time + timedelta(hours=step.delay_hours)
            
            # Prepare email context
            email_context = {
                **request.context,
                "user_id": request.user_id,
                "sequence_name": request.sequence_name,
                "sequence_day": step.day,
                "dashboard_url": settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={request.email}",
                "preferences_url": f"{settings.PREFERENCES_BASE_URL}?email={request.email}",
            }
            
            # Queue email with scheduled delivery time
            job = email_queue.enqueue_at(
                delivery_time,
                'app.tasks.email_tasks.send_sequence_email',
                to_email=request.email,
                template_name=step.template_name,
                subject=step.subject,
                context=email_context,
                job_id=f"seq_{request.sequence_name}_{request.user_id}_day{step.day}",
                job_timeout='10m'
            )
            
            scheduled_count += 1
            
            logger.info(
                f"Scheduled sequence email",
                extra={
                    "user_id": request.user_id,
                    "email": request.email,
                    "sequence": request.sequence_name,
                    "day": step.day,
                    "template": step.template_name,
                    "delivery_time": delivery_time.isoformat(),
                    "job_id": job.id
                }
            )
        
        logger.info(
            f"User enrolled in sequence",
            extra={
                "user_id": request.user_id,
                "email": request.email,
                "sequence": request.sequence_name,
                "scheduled_emails": scheduled_count
            }
        )
        
        return EnrollSequenceResponse(
            success=True,
            message=f"Successfully enrolled in {request.sequence_name} sequence",
            sequence_name=request.sequence_name,
            total_emails=len(sequence),
            scheduled_jobs=scheduled_count,
            enrollment_id=f"{request.user_id}_{request.sequence_name}_{int(enrollment_time.timestamp())}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to enroll user in sequence",
            extra={
                "user_id": request.user_id,
                "email": request.email,
                "sequence": request.sequence_name,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enroll in sequence: {str(e)}"
        )


@router.get("/metadata/{sequence_name}")
async def get_sequence_info(sequence_name: str) -> Dict[str, Any]:
    """
    Get metadata about an email sequence
    
    Args:
        sequence_name: Name of the sequence (e.g., 'onboarding')
        
    Returns:
        Sequence metadata including steps, duration, and description
        
    Raises:
        HTTPException: If sequence not found
    """
    try:
        if sequence_name == "onboarding":
            metadata = get_onboarding_metadata()
        elif sequence_name == "lead_magnet":
            metadata = get_lead_magnet_metadata()
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Sequence not found: {sequence_name}. Supported sequences: 'onboarding', 'lead_magnet'"
            )
        
        return metadata
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sequence metadata: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sequence metadata: {str(e)}"
        )


@router.post("/cancel")
async def cancel_sequence_enrollment(
    user_id: str,
    sequence_name: str
) -> Dict[str, Any]:
    """
    Cancel a user's enrollment in a sequence
    
    Removes all pending scheduled emails for the user in the specified sequence.
    
    Args:
        user_id: User ID
        sequence_name: Name of the sequence to cancel
        
    Returns:
        Cancellation status and count of cancelled jobs
        
    Raises:
        HTTPException: If cancellation fails
    """
    try:
        # Get all jobs for this user's sequence
        cancelled_count = 0
        
        # Get appropriate sequence
        if sequence_name == "onboarding":
            sequence = get_onboarding_sequence()
        elif sequence_name == "lead_magnet":
            sequence = get_lead_magnet_sequence()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown sequence: {sequence_name}"
            )
        
        for step in sequence:
            job_id = f"seq_{sequence_name}_{user_id}_day{step.day}"
            
            try:
                # Try to cancel the job
                job = email_queue.fetch_job(job_id)
                if job and job.get_status() in ['queued', 'scheduled']:
                    job.cancel()
                    job.delete()
                    cancelled_count += 1
                    logger.info(f"Cancelled job {job_id}")
            except Exception as e:
                logger.warning(f"Could not cancel job {job_id}: {str(e)}")
                continue
        
        logger.info(
            f"Sequence enrollment cancelled",
            extra={
                "user_id": user_id,
                "sequence": sequence_name,
                "cancelled_jobs": cancelled_count
            }
        )
        
        return {
            "success": True,
            "message": f"Cancelled {cancelled_count} scheduled emails",
            "user_id": user_id,
            "sequence_name": sequence_name,
            "cancelled_jobs": cancelled_count
        }
        
    except Exception as e:
        logger.error(
            f"Failed to cancel sequence enrollment",
            extra={
                "user_id": user_id,
                "sequence": sequence_name,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel sequence: {str(e)}"
        )
