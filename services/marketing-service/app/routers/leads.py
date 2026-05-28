"""
Lead Capture Router
Handles lead magnet downloads and email capture
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from rq import Queue

from app.config import settings
from app.tasks.email_tasks import redis_conn
from app.data.sequences.lead_magnet import get_lead_magnet_content

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize email queue
email_queue = Queue('emails', connection=redis_conn)


# In-memory lead storage (replace with database in production)
# This is a temporary solution for MVP - should be replaced with PostgreSQL
leads_db: Dict[str, Dict[str, Any]] = {}


# Request/Response Models

class LeadCaptureRequest(BaseModel):
    """Request to capture a lead"""
    email: EmailStr
    source: str  # 'popup', 'inline', 'footer', 'lead_magnet'
    lead_magnet_id: Optional[str] = None
    page_url: str
    utm_params: Optional[Dict[str, str]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "trader@example.com",
                "source": "lead_magnet",
                "lead_magnet_id": "fo-trading-checklist",
                "page_url": "https://signalixai.com/resources/fo-trading-checklist",
                "utm_params": {
                    "utm_source": "google",
                    "utm_medium": "cpc",
                    "utm_campaign": "lead_magnets"
                }
            }
        }


class LeadCaptureResponse(BaseModel):
    """Response after capturing a lead"""
    success: bool
    message: str
    lead_id: str
    download_url: Optional[str] = None
    is_new_lead: bool


class LeadStats(BaseModel):
    """Lead statistics"""
    total_leads: int
    new_today: int
    by_source: Dict[str, int]
    by_lead_magnet: Dict[str, int]


# Lead magnet download URLs (in production, these would be in database or S3)
LEAD_MAGNET_DOWNLOADS: Dict[str, str] = {
    "fo-trading-checklist": "https://signalixai.com/downloads/fo-trading-checklist.pdf",
    "options-greeks-cheat-sheet": "https://signalixai.com/downloads/options-greeks-cheat-sheet.pdf",
    "position-sizing-calculator": "https://signalixai.com/downloads/position-sizing-calculator.xlsx",
    "backtesting-template": "https://signalixai.com/downloads/backtesting-template.xlsx",
    "ai-trading-signals-guide": "https://signalixai.com/downloads/ai-trading-signals-guide.pdf",
}


# Endpoints

@router.post("/capture", response_model=LeadCaptureResponse)
async def capture_lead(
    request: LeadCaptureRequest,
    background_tasks: BackgroundTasks
) -> LeadCaptureResponse:
    """
    Capture a lead and optionally deliver lead magnet
    
    This endpoint:
    1. Checks if email already exists (deduplication)
    2. Creates new lead or updates existing lead's sources
    3. Delivers lead magnet if requested
    4. Auto-enrolls in lead magnet nurture sequence
    
    Args:
        request: Lead capture request with email, source, and optional lead magnet
        
    Returns:
        LeadCaptureResponse with success status, lead_id, and download URL
        
    Raises:
        HTTPException: If lead capture fails
    """
    try:
        email = request.email.lower()
        is_new_lead = False
        
        # Check if lead already exists
        if email in leads_db:
            lead = leads_db[email]
            
            # Update sources if new source
            if request.source not in lead["sources"]:
                lead["sources"].append(request.source)
                lead["updated_at"] = datetime.utcnow().isoformat()
            
            # Update lead magnet if provided
            if request.lead_magnet_id and request.lead_magnet_id not in lead.get("lead_magnets", []):
                if "lead_magnets" not in lead:
                    lead["lead_magnets"] = []
                lead["lead_magnets"].append(request.lead_magnet_id)
            
            logger.info(
                f"Existing lead updated",
                extra={
                    "email": email,
                    "source": request.source,
                    "lead_magnet": request.lead_magnet_id
                }
            )
        else:
            # Create new lead
            lead_id = f"lead_{int(datetime.utcnow().timestamp() * 1000)}"
            lead = {
                "id": lead_id,
                "email": email,
                "source": request.source,
                "sources": [request.source],
                "lead_magnets": [request.lead_magnet_id] if request.lead_magnet_id else [],
                "page_url": request.page_url,
                "utm_params": request.utm_params or {},
                "status": "active",
                "converted_to_user": False,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            leads_db[email] = lead
            is_new_lead = True
            
            logger.info(
                f"New lead captured",
                extra={
                    "lead_id": lead_id,
                    "email": email,
                    "source": request.source,
                    "lead_magnet": request.lead_magnet_id
                }
            )
        
        # Get download URL if lead magnet requested
        download_url = None
        if request.lead_magnet_id:
            download_url = LEAD_MAGNET_DOWNLOADS.get(request.lead_magnet_id)
            
            if not download_url:
                logger.warning(f"Unknown lead magnet: {request.lead_magnet_id}")
            else:
                # Auto-enroll in lead magnet nurture sequence
                background_tasks.add_task(
                    enroll_in_lead_magnet_sequence,
                    email=email,
                    lead_magnet_id=request.lead_magnet_id
                )
        
        return LeadCaptureResponse(
            success=True,
            message="Successfully subscribed" if is_new_lead else "Email already subscribed",
            lead_id=lead["id"],
            download_url=download_url,
            is_new_lead=is_new_lead
        )
        
    except Exception as e:
        logger.error(
            f"Failed to capture lead",
            extra={
                "email": request.email,
                "source": request.source,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture lead: {str(e)}"
        )


@router.get("/stats", response_model=LeadStats)
async def get_lead_stats() -> LeadStats:
    """
    Get lead statistics
    
    Returns:
        LeadStats with total leads, new today, and breakdowns by source and lead magnet
    """
    try:
        total_leads = len(leads_db)
        
        # Count new leads today
        today = datetime.utcnow().date()
        new_today = sum(
            1 for lead in leads_db.values()
            if datetime.fromisoformat(lead["created_at"]).date() == today
        )
        
        # Count by source
        by_source: Dict[str, int] = {}
        for lead in leads_db.values():
            for source in lead["sources"]:
                by_source[source] = by_source.get(source, 0) + 1
        
        # Count by lead magnet
        by_lead_magnet: Dict[str, int] = {}
        for lead in leads_db.values():
            for magnet in lead.get("lead_magnets", []):
                by_lead_magnet[magnet] = by_lead_magnet.get(magnet, 0) + 1
        
        return LeadStats(
            total_leads=total_leads,
            new_today=new_today,
            by_source=by_source,
            by_lead_magnet=by_lead_magnet
        )
        
    except Exception as e:
        logger.error(f"Failed to get lead stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve lead stats: {str(e)}"
        )


@router.get("/lead/{email}")
async def get_lead(email: str) -> Dict[str, Any]:
    """
    Get lead details by email
    
    Args:
        email: Lead email address
        
    Returns:
        Lead details
        
    Raises:
        HTTPException: If lead not found
    """
    email = email.lower()
    
    if email not in leads_db:
        raise HTTPException(
            status_code=404,
            detail=f"Lead not found: {email}"
        )
    
    return leads_db[email]


# Helper Functions

def enroll_in_lead_magnet_sequence(email: str, lead_magnet_id: str) -> None:
    """
    Auto-enroll lead in lead magnet nurture sequence
    
    This is called as a background task after lead capture.
    It enrolls the lead in the 4-email nurture sequence.
    
    Args:
        email: Lead email address
        lead_magnet_id: ID of the lead magnet downloaded
    """
    try:
        # Get lead magnet content for personalization
        magnet_content = get_lead_magnet_content(lead_magnet_id)
        
        # Import here to avoid circular dependency
        from app.routers.sequences import email_queue
        from app.data.sequences.lead_magnet import get_lead_magnet_sequence
        from datetime import timedelta
        
        sequence = get_lead_magnet_sequence()
        enrollment_time = datetime.utcnow()
        
        for step in sequence:
            # Calculate delivery time
            delivery_time = enrollment_time + timedelta(hours=step.delay_hours)
            
            # Prepare email context with lead magnet personalization
            email_context = {
                "email": email,
                "lead_magnet_id": lead_magnet_id,
                "lead_magnet_title": magnet_content["title"],
                "topic": magnet_content["topic"],
                "category": magnet_content["category"],
                "related_resources": magnet_content["related_resources"],
                "download_url": LEAD_MAGNET_DOWNLOADS.get(lead_magnet_id, ""),
                "dashboard_url": settings.DASHBOARD_URL,
                "signup_url": f"{settings.DASHBOARD_URL}/signup",
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={email}",
                "preferences_url": f"{settings.PREFERENCES_BASE_URL}?email={email}",
            }
            
            # Personalize subject line
            subject = step.subject.replace("{{lead_magnet_title}}", magnet_content["title"])
            subject = subject.replace("{{topic}}", magnet_content["topic"])
            
            # Queue email with scheduled delivery time
            job = email_queue.enqueue_at(
                delivery_time,
                'app.tasks.email_tasks.send_sequence_email',
                to_email=email,
                template_name=step.template_name,
                subject=subject,
                context=email_context,
                job_id=f"seq_lead_magnet_{email}_{lead_magnet_id}_day{step.day}",
                job_timeout='10m'
            )
            
            logger.info(
                f"Scheduled lead magnet sequence email",
                extra={
                    "email": email,
                    "lead_magnet": lead_magnet_id,
                    "day": step.day,
                    "template": step.template_name,
                    "delivery_time": delivery_time.isoformat(),
                    "job_id": job.id
                }
            )
        
        logger.info(
            f"Lead enrolled in lead magnet sequence",
            extra={
                "email": email,
                "lead_magnet": lead_magnet_id,
                "scheduled_emails": len(sequence)
            }
        )
        
    except Exception as e:
        logger.error(
            f"Failed to enroll lead in sequence",
            extra={
                "email": email,
                "lead_magnet": lead_magnet_id,
                "error": str(e)
            }
        )
        # Don't raise - this is a background task, we don't want to fail the main request
