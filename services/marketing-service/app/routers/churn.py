"""
Churn Prevention Router
Handles cancel flow, save offers, dunning, and churn signal detection

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
from enum import Enum

from app.config import settings
from app.services.churn_signals import churn_detection_service

logger = logging.getLogger(__name__)

router = APIRouter()


# In-memory storage (replace with database in production)
cancel_surveys_db: Dict[str, Dict[str, Any]] = {}
retention_discounts_db: Dict[str, Dict[str, Any]] = {}
subscription_pauses_db: Dict[str, Dict[str, Any]] = {}
cancellations_db: Dict[str, Dict[str, Any]] = {}
payment_failures_db: Dict[str, Dict[str, Any]] = {}
churn_signals_db: Dict[str, Dict[str, Any]] = {}


# Enums and Constants

class CancelReason(str, Enum):
    """Cancel reasons"""
    TOO_EXPENSIVE = "too_expensive"
    NOT_USING_ENOUGH = "not_using_enough"
    MISSING_FEATURES = "missing_features"
    SWITCHING_COMPETITOR = "switching_competitor"
    TECHNICAL_ISSUES = "technical_issues"
    TEMPORARY_NEED = "temporary_need"
    BUSINESS_CLOSED = "business_closed"
    OTHER = "other"


class SaveOfferType(str, Enum):
    """Save offer types"""
    DISCOUNT = "discount"
    PAUSE = "pause"
    DOWNGRADE = "downgrade"
    SUPPORT = "support"
    ROADMAP = "roadmap"


# Save offer mapping based on cancel reason
SAVE_OFFER_MAPPING: Dict[CancelReason, Optional[SaveOfferType]] = {
    CancelReason.TOO_EXPENSIVE: SaveOfferType.DISCOUNT,
    CancelReason.NOT_USING_ENOUGH: SaveOfferType.PAUSE,
    CancelReason.MISSING_FEATURES: SaveOfferType.ROADMAP,
    CancelReason.SWITCHING_COMPETITOR: SaveOfferType.DISCOUNT,
    CancelReason.TECHNICAL_ISSUES: SaveOfferType.SUPPORT,
    CancelReason.TEMPORARY_NEED: SaveOfferType.PAUSE,
    CancelReason.BUSINESS_CLOSED: None,
    CancelReason.OTHER: None,
}


# Request/Response Models

class CancelSurveyRequest(BaseModel):
    """Request to submit cancel survey"""
    user_id: str
    reason: CancelReason
    feedback: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "reason": "too_expensive",
                "feedback": "Great product but too expensive for my trading volume"
            }
        }


class SaveOffer(BaseModel):
    """Save offer details"""
    type: SaveOfferType
    title: str
    description: str
    cta_text: str
    value: Optional[str] = None


class CancelSurveyResponse(BaseModel):
    """Response after submitting cancel survey"""
    success: bool
    has_offer: bool
    offer: Optional[SaveOffer] = None


class ApplyDiscountRequest(BaseModel):
    """Request to apply retention discount"""
    user_id: str
    discount_code: str


class ApplyDiscountResponse(BaseModel):
    """Response after applying discount"""
    success: bool
    message: str
    discount_percentage: int
    duration_months: int


class PauseSubscriptionRequest(BaseModel):
    """Request to pause subscription"""
    user_id: str
    pause_months: int  # 1-3 months


class PauseSubscriptionResponse(BaseModel):
    """Response after pausing subscription"""
    success: bool
    message: str
    resume_date: str


class ConfirmCancellationRequest(BaseModel):
    """Request to confirm cancellation"""
    user_id: str


class ConfirmCancellationResponse(BaseModel):
    """Response after confirming cancellation"""
    success: bool
    message: str
    effective_date: str


class PaymentFailureWebhook(BaseModel):
    """Webhook payload for payment failure"""
    user_id: str
    subscription_id: str
    amount: float
    currency: str
    failure_reason: str


class ChurnSignal(BaseModel):
    """Churn signal detection"""
    user_id: str
    signal_type: str
    signal_strength: str  # 'low', 'medium', 'high'
    signal_value: Dict[str, Any]
    detected_at: str


# Endpoints

@router.post("/cancel-survey", response_model=CancelSurveyResponse)
async def submit_cancel_survey(
    request: CancelSurveyRequest,
    background_tasks: BackgroundTasks
) -> CancelSurveyResponse:
    """
    Submit cancel survey and get dynamic save offer
    
    This endpoint:
    1. Records the cancel survey response
    2. Determines appropriate save offer based on reason
    3. Returns save offer details if available
    
    Args:
        request: Cancel survey with user_id, reason, and optional feedback
        
    Returns:
        CancelSurveyResponse with save offer if available
    """
    try:
        # Record survey
        survey_id = f"survey_{int(datetime.utcnow().timestamp() * 1000)}"
        survey = {
            "id": survey_id,
            "user_id": request.user_id,
            "reason": request.reason.value,
            "feedback": request.feedback,
            "created_at": datetime.utcnow().isoformat()
        }
        cancel_surveys_db[survey_id] = survey
        
        logger.info(
            f"Cancel survey submitted",
            extra={
                "survey_id": survey_id,
                "user_id": request.user_id,
                "reason": request.reason.value
            }
        )
        
        # Get save offer based on reason
        save_offer = get_save_offer(request.reason)
        
        # Track event
        background_tasks.add_task(
            track_cancel_event,
            user_id=request.user_id,
            event="cancel_survey_submitted",
            properties={"reason": request.reason.value}
        )
        
        return CancelSurveyResponse(
            success=True,
            has_offer=save_offer is not None,
            offer=save_offer
        )
        
    except Exception as e:
        logger.error(
            f"Failed to submit cancel survey",
            extra={
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit cancel survey: {str(e)}"
        )


@router.post("/apply-discount", response_model=ApplyDiscountResponse)
async def apply_retention_discount(
    request: ApplyDiscountRequest,
    background_tasks: BackgroundTasks
) -> ApplyDiscountResponse:
    """
    Apply retention discount to user subscription
    
    This endpoint:
    1. Validates the discount code
    2. Applies 25% discount for 3 months
    3. Updates subscription in payment provider (Stripe/Razorpay)
    
    Args:
        request: Apply discount request with user_id and discount_code
        
    Returns:
        ApplyDiscountResponse with discount details
    """
    try:
        # Validate discount code
        if request.discount_code != "RETENTION25":
            raise HTTPException(
                status_code=400,
                detail="Invalid discount code"
            )
        
        # Check if user already has active discount
        existing_discount = next(
            (d for d in retention_discounts_db.values() 
             if d["user_id"] == request.user_id and d["status"] == "active"),
            None
        )
        
        if existing_discount:
            raise HTTPException(
                status_code=400,
                detail="User already has an active retention discount"
            )
        
        # Create discount record
        discount_id = f"discount_{int(datetime.utcnow().timestamp() * 1000)}"
        discount = {
            "id": discount_id,
            "user_id": request.user_id,
            "discount_code": request.discount_code,
            "discount_percentage": 25,
            "duration_months": 3,
            "status": "active",
            "applied_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=90)).isoformat()
        }
        retention_discounts_db[discount_id] = discount
        
        logger.info(
            f"Retention discount applied",
            extra={
                "discount_id": discount_id,
                "user_id": request.user_id,
                "discount_percentage": 25,
                "duration_months": 3
            }
        )
        
        # TODO: Update subscription in Stripe/Razorpay
        # await update_subscription_discount(request.user_id, request.discount_code)
        
        # Track save event
        background_tasks.add_task(
            track_cancel_event,
            user_id=request.user_id,
            event="cancel_flow_saved",
            properties={"save_method": "discount"}
        )
        
        return ApplyDiscountResponse(
            success=True,
            message="Discount applied successfully",
            discount_percentage=25,
            duration_months=3
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to apply discount",
            extra={
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply discount: {str(e)}"
        )


@router.post("/pause-subscription", response_model=PauseSubscriptionResponse)
async def pause_subscription(
    request: PauseSubscriptionRequest,
    background_tasks: BackgroundTasks
) -> PauseSubscriptionResponse:
    """
    Pause user subscription for specified months
    
    This endpoint:
    1. Validates pause duration (1-3 months)
    2. Pauses subscription in payment provider
    3. Schedules auto-reactivation
    4. Sends reactivation reminder email
    
    Args:
        request: Pause subscription request with user_id and pause_months
        
    Returns:
        PauseSubscriptionResponse with resume date
    """
    try:
        # Validate pause duration
        if request.pause_months < 1 or request.pause_months > 3:
            raise HTTPException(
                status_code=400,
                detail="Pause duration must be between 1 and 3 months"
            )
        
        # Calculate resume date
        resume_date = datetime.utcnow() + timedelta(days=30 * request.pause_months)
        
        # Create pause record
        pause_id = f"pause_{int(datetime.utcnow().timestamp() * 1000)}"
        pause = {
            "id": pause_id,
            "user_id": request.user_id,
            "pause_months": request.pause_months,
            "paused_at": datetime.utcnow().isoformat(),
            "resume_date": resume_date.isoformat(),
            "status": "active"
        }
        subscription_pauses_db[pause_id] = pause
        
        logger.info(
            f"Subscription paused",
            extra={
                "pause_id": pause_id,
                "user_id": request.user_id,
                "pause_months": request.pause_months,
                "resume_date": resume_date.isoformat()
            }
        )
        
        # TODO: Update subscription status in payment provider
        # await update_subscription_status(request.user_id, "paused", resume_date)
        
        # Schedule reactivation reminder email (3 days before resume)
        reminder_date = resume_date - timedelta(days=3)
        background_tasks.add_task(
            schedule_reactivation_reminder,
            user_id=request.user_id,
            send_at=reminder_date
        )
        
        # Track save event
        background_tasks.add_task(
            track_cancel_event,
            user_id=request.user_id,
            event="cancel_flow_saved",
            properties={
                "save_method": "pause",
                "pause_months": request.pause_months
            }
        )
        
        return PauseSubscriptionResponse(
            success=True,
            message=f"Subscription paused for {request.pause_months} months",
            resume_date=resume_date.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to pause subscription",
            extra={
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause subscription: {str(e)}"
        )


@router.post("/confirm-cancellation", response_model=ConfirmCancellationResponse)
async def confirm_cancellation(
    request: ConfirmCancellationRequest,
    background_tasks: BackgroundTasks
) -> ConfirmCancellationResponse:
    """
    Process final cancellation
    
    This endpoint:
    1. Cancels subscription in payment provider
    2. Records cancellation with effective date
    3. Sends cancellation confirmation email
    
    Args:
        request: Confirm cancellation request with user_id
        
    Returns:
        ConfirmCancellationResponse with effective date
    """
    try:
        # Calculate effective date (end of current billing period, ~30 days)
        effective_date = datetime.utcnow() + timedelta(days=30)
        
        # Create cancellation record
        cancellation_id = f"cancel_{int(datetime.utcnow().timestamp() * 1000)}"
        cancellation = {
            "id": cancellation_id,
            "user_id": request.user_id,
            "cancelled_at": datetime.utcnow().isoformat(),
            "effective_date": effective_date.isoformat(),
            "status": "pending"
        }
        cancellations_db[cancellation_id] = cancellation
        
        logger.info(
            f"Subscription cancelled",
            extra={
                "cancellation_id": cancellation_id,
                "user_id": request.user_id,
                "effective_date": effective_date.isoformat()
            }
        )
        
        # TODO: Cancel subscription in payment provider
        # await cancel_subscription(request.user_id)
        
        # Send cancellation confirmation email
        background_tasks.add_task(
            send_cancellation_email,
            user_id=request.user_id,
            effective_date=effective_date
        )
        
        # Track cancellation event
        background_tasks.add_task(
            track_cancel_event,
            user_id=request.user_id,
            event="subscription_cancelled",
            properties={"effective_date": effective_date.isoformat()}
        )
        
        return ConfirmCancellationResponse(
            success=True,
            message="Subscription cancelled successfully",
            effective_date=effective_date.isoformat()
        )
        
    except Exception as e:
        logger.error(
            f"Failed to confirm cancellation",
            extra={
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to confirm cancellation: {str(e)}"
        )


@router.post("/payment-failure-webhook")
async def handle_payment_failure(
    webhook: PaymentFailureWebhook,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Handle payment failure webhook from Stripe/Razorpay
    
    This endpoint:
    1. Records payment failure
    2. Initiates immediate retry
    3. Schedules dunning sequence if retry fails
    4. Sends payment failed email
    
    Args:
        webhook: Payment failure webhook payload
        
    Returns:
        Success response
    """
    try:
        # Record failure
        failure_id = f"failure_{int(datetime.utcnow().timestamp() * 1000)}"
        failure = {
            "id": failure_id,
            "user_id": webhook.user_id,
            "subscription_id": webhook.subscription_id,
            "amount": webhook.amount,
            "currency": webhook.currency,
            "failure_reason": webhook.failure_reason,
            "failed_at": datetime.utcnow().isoformat(),
            "retry_count": 0,
            "status": "pending"
        }
        payment_failures_db[failure_id] = failure
        
        logger.info(
            f"Payment failure recorded",
            extra={
                "failure_id": failure_id,
                "user_id": webhook.user_id,
                "subscription_id": webhook.subscription_id,
                "amount": webhook.amount
            }
        )
        
        # Immediate retry
        background_tasks.add_task(
            retry_payment,
            failure_id=failure_id
        )
        
        # Send payment failed email
        background_tasks.add_task(
            send_payment_failed_email,
            user_id=webhook.user_id,
            retry_date=(datetime.utcnow() + timedelta(days=3)).isoformat()
        )
        
        return {"success": True, "message": "Payment failure processed"}
        
    except Exception as e:
        logger.error(
            f"Failed to handle payment failure",
            extra={
                "user_id": webhook.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to handle payment failure: {str(e)}"
        )


@router.post("/detect-churn-signals/{user_id}")
async def detect_churn_signals(
    user_id: str,
    background_tasks: BackgroundTasks
) -> List[ChurnSignal]:
    """
    Detect churn signals for a user
    
    This endpoint runs all churn detection checks:
    1. Login frequency drop (>50% vs prior 7 days)
    2. Feature usage stopped
    3. Support ticket pattern changes
    4. Billing page visits increased
    
    Args:
        user_id: User ID to check for churn signals
        
    Returns:
        List of detected churn signals
    """
    try:
        # Use churn detection service
        signals_data = await churn_detection_service.detect_churn_signals(user_id)
        
        # Convert to ChurnSignal models
        signals = [
            ChurnSignal(
                user_id=user_id,
                signal_type=s["signal_type"],
                signal_strength=s["signal_strength"],
                signal_value=s["signal_value"],
                detected_at=s["detected_at"]
            )
            for s in signals_data
        ]
        
        # Store signals in database
        for signal in signals:
            signal_id = f"signal_{int(datetime.utcnow().timestamp() * 1000)}"
            churn_signals_db[signal_id] = {
                "id": signal_id,
                **signal.dict()
            }
        
        logger.info(
            f"Churn signals detected",
            extra={
                "user_id": user_id,
                "signal_count": len(signals)
            }
        )
        
        return signals
        
    except Exception as e:
        logger.error(
            f"Failed to detect churn signals",
            extra={
                "user_id": user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect churn signals: {str(e)}"
        )


# Helper Functions

def get_save_offer(reason: CancelReason) -> Optional[SaveOffer]:
    """
    Get save offer based on cancel reason
    
    Args:
        reason: Cancel reason
        
    Returns:
        SaveOffer if available, None otherwise
    """
    offer_type = SAVE_OFFER_MAPPING.get(reason)
    
    if not offer_type:
        return None
    
    if offer_type == SaveOfferType.DISCOUNT:
        return SaveOffer(
            type=SaveOfferType.DISCOUNT,
            title="Get 25% off for 3 months",
            description="We value your business. Stay with us and get 25% off your next 3 months.",
            cta_text="Apply Discount",
            value="25% off"
        )
    elif offer_type == SaveOfferType.PAUSE:
        return SaveOffer(
            type=SaveOfferType.PAUSE,
            title="Pause your subscription",
            description="Take a break for 1-3 months. Your data and settings will be saved.",
            cta_text="Pause Subscription"
        )
    elif offer_type == SaveOfferType.DOWNGRADE:
        return SaveOffer(
            type=SaveOfferType.DOWNGRADE,
            title="Downgrade to a lower plan",
            description="Keep using SignalixAI at a lower price point that fits your needs.",
            cta_text="View Plans"
        )
    elif offer_type == SaveOfferType.SUPPORT:
        return SaveOffer(
            type=SaveOfferType.SUPPORT,
            title="Let us help you",
            description="Our support team can resolve technical issues. Get priority support now.",
            cta_text="Contact Support"
        )
    elif offer_type == SaveOfferType.ROADMAP:
        return SaveOffer(
            type=SaveOfferType.ROADMAP,
            title="See what's coming",
            description="We're building the features you need. Check our roadmap and stay for what's next.",
            cta_text="View Roadmap"
        )
    
    return None


async def track_cancel_event(user_id: str, event: str, properties: Dict[str, Any]) -> None:
    """Track cancel flow event"""
    logger.info(
        f"Cancel event tracked",
        extra={
            "user_id": user_id,
            "event": event,
            "properties": properties
        }
    )
    # TODO: Send to analytics service


async def schedule_reactivation_reminder(user_id: str, send_at: datetime) -> None:
    """Schedule reactivation reminder email"""
    logger.info(
        f"Reactivation reminder scheduled",
        extra={
            "user_id": user_id,
            "send_at": send_at.isoformat()
        }
    )
    # TODO: Queue email with scheduled delivery


async def send_cancellation_email(user_id: str, effective_date: datetime) -> None:
    """Send cancellation confirmation email"""
    logger.info(
        f"Cancellation email sent",
        extra={
            "user_id": user_id,
            "effective_date": effective_date.isoformat()
        }
    )
    # TODO: Send via email service


async def retry_payment(failure_id: str) -> None:
    """Retry failed payment"""
    logger.info(
        f"Payment retry initiated",
        extra={"failure_id": failure_id}
    )
    # TODO: Implement payment retry logic


async def send_payment_failed_email(user_id: str, retry_date: str) -> None:
    """Send payment failed email"""
    logger.info(
        f"Payment failed email sent",
        extra={
            "user_id": user_id,
            "retry_date": retry_date
        }
    )
    # TODO: Send via email service


async def trigger_retention_actions(user_id: str, signals: List[ChurnSignal]) -> None:
    """Trigger retention actions based on churn signals"""
    logger.info(
        f"Retention actions triggered",
        extra={
            "user_id": user_id,
            "signal_count": len(signals)
        }
    )
    # TODO: Implement retention actions
