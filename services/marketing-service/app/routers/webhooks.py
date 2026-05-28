"""
Webhooks Router
Handles payment provider webhooks (Stripe/Razorpay)

Requirements: 11.6
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import hmac
import hashlib

from app.config import settings
from app.services.dunning_service import dunning_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Request Models

class StripeWebhookEvent(BaseModel):
    """Stripe webhook event"""
    id: str
    type: str
    data: Dict[str, Any]
    created: int


class RazorpayWebhookEvent(BaseModel):
    """Razorpay webhook event"""
    event: str
    payload: Dict[str, Any]
    created_at: int


# Endpoints

@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
) -> Dict[str, Any]:
    """
    Handle Stripe webhook events
    
    Supported events:
    - invoice.payment_failed: Payment failure
    - invoice.payment_succeeded: Payment success
    - customer.subscription.deleted: Subscription cancelled
    - customer.subscription.updated: Subscription updated
    
    Args:
        request: FastAPI request object
        background_tasks: Background tasks
        stripe_signature: Stripe signature header for verification
        
    Returns:
        Success response
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify webhook signature (in production)
        # if not _verify_stripe_signature(body, stripe_signature):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse event
        event_data = await request.json()
        event_type = event_data.get("type")
        event_id = event_data.get("id")
        data = event_data.get("data", {}).get("object", {})
        
        logger.info(
            f"Stripe webhook received",
            extra={
                "event_id": event_id,
                "event_type": event_type
            }
        )
        
        # Handle different event types
        if event_type == "invoice.payment_failed":
            await _handle_payment_failed(data, background_tasks)
        
        elif event_type == "invoice.payment_succeeded":
            await _handle_payment_succeeded(data, background_tasks)
        
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(data, background_tasks)
        
        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(data, background_tasks)
        
        else:
            logger.info(
                f"Unhandled Stripe event type",
                extra={"event_type": event_type}
            )
        
        return {"success": True, "event_id": event_id}
        
    except Exception as e:
        logger.error(
            f"Failed to handle Stripe webhook",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )


@router.post("/razorpay")
async def handle_razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")
) -> Dict[str, Any]:
    """
    Handle Razorpay webhook events
    
    Supported events:
    - payment.failed: Payment failure
    - payment.captured: Payment success
    - subscription.cancelled: Subscription cancelled
    - subscription.updated: Subscription updated
    
    Args:
        request: FastAPI request object
        background_tasks: Background tasks
        x_razorpay_signature: Razorpay signature header for verification
        
    Returns:
        Success response
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify webhook signature (in production)
        # if not _verify_razorpay_signature(body, x_razorpay_signature):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse event
        event_data = await request.json()
        event_type = event_data.get("event")
        payload = event_data.get("payload", {})
        
        logger.info(
            f"Razorpay webhook received",
            extra={"event_type": event_type}
        )
        
        # Handle different event types
        if event_type == "payment.failed":
            await _handle_razorpay_payment_failed(payload, background_tasks)
        
        elif event_type == "payment.captured":
            await _handle_razorpay_payment_captured(payload, background_tasks)
        
        elif event_type == "subscription.cancelled":
            await _handle_razorpay_subscription_cancelled(payload, background_tasks)
        
        elif event_type == "subscription.updated":
            await _handle_razorpay_subscription_updated(payload, background_tasks)
        
        else:
            logger.info(
                f"Unhandled Razorpay event type",
                extra={"event_type": event_type}
            )
        
        return {"success": True}
        
    except Exception as e:
        logger.error(
            f"Failed to handle Razorpay webhook",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )


# Helper Functions - Stripe

async def _handle_payment_failed(data: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Stripe payment failure"""
    try:
        # Extract payment details
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        amount = data.get("amount_due", 0) / 100  # Convert from cents
        currency = data.get("currency", "usd").upper()
        failure_reason = data.get("last_payment_error", {}).get("message", "Unknown")
        
        # Get user_id from customer_id (would query database in production)
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Processing Stripe payment failure",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id,
                "amount": amount,
                "currency": currency
            }
        )
        
        # Handle payment failure with dunning service
        background_tasks.add_task(
            dunning_service.handle_payment_failure,
            user_id=user_id,
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            failure_reason=failure_reason
        )
        
    except Exception as e:
        logger.error(
            f"Failed to handle Stripe payment failure",
            extra={"error": str(e)}
        )


async def _handle_payment_succeeded(data: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Stripe payment success"""
    try:
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        amount = data.get("amount_paid", 0) / 100
        currency = data.get("currency", "usd").upper()
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Stripe payment succeeded",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id,
                "amount": amount,
                "currency": currency
            }
        )
        
        # TODO: Update subscription status, send receipt email
        
    except Exception as e:
        logger.error(
            f"Failed to handle Stripe payment success",
            extra={"error": str(e)}
        )


async def _handle_subscription_deleted(data: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Stripe subscription deletion"""
    try:
        customer_id = data.get("customer")
        subscription_id = data.get("id")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Stripe subscription deleted",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id
            }
        )
        
        # TODO: Update subscription status in database
        
    except Exception as e:
        logger.error(
            f"Failed to handle Stripe subscription deletion",
            extra={"error": str(e)}
        )


async def _handle_subscription_updated(data: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Stripe subscription update"""
    try:
        customer_id = data.get("customer")
        subscription_id = data.get("id")
        status = data.get("status")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Stripe subscription updated",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id,
                "status": status
            }
        )
        
        # TODO: Update subscription status in database
        
    except Exception as e:
        logger.error(
            f"Failed to handle Stripe subscription update",
            extra={"error": str(e)}
        )


# Helper Functions - Razorpay

async def _handle_razorpay_payment_failed(payload: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Razorpay payment failure"""
    try:
        payment = payload.get("payment", {}).get("entity", {})
        subscription = payload.get("subscription", {}).get("entity", {})
        
        customer_id = payment.get("customer_id")
        subscription_id = subscription.get("id")
        amount = payment.get("amount", 0) / 100  # Convert from paise
        currency = payment.get("currency", "INR")
        failure_reason = payment.get("error_description", "Unknown")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Processing Razorpay payment failure",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id,
                "amount": amount,
                "currency": currency
            }
        )
        
        # Handle payment failure with dunning service
        background_tasks.add_task(
            dunning_service.handle_payment_failure,
            user_id=user_id,
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            failure_reason=failure_reason
        )
        
    except Exception as e:
        logger.error(
            f"Failed to handle Razorpay payment failure",
            extra={"error": str(e)}
        )


async def _handle_razorpay_payment_captured(payload: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Razorpay payment capture"""
    try:
        payment = payload.get("payment", {}).get("entity", {})
        
        customer_id = payment.get("customer_id")
        amount = payment.get("amount", 0) / 100
        currency = payment.get("currency", "INR")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Razorpay payment captured",
            extra={
                "user_id": user_id,
                "amount": amount,
                "currency": currency
            }
        )
        
        # TODO: Update subscription status, send receipt email
        
    except Exception as e:
        logger.error(
            f"Failed to handle Razorpay payment capture",
            extra={"error": str(e)}
        )


async def _handle_razorpay_subscription_cancelled(payload: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Razorpay subscription cancellation"""
    try:
        subscription = payload.get("subscription", {}).get("entity", {})
        
        customer_id = subscription.get("customer_id")
        subscription_id = subscription.get("id")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Razorpay subscription cancelled",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id
            }
        )
        
        # TODO: Update subscription status in database
        
    except Exception as e:
        logger.error(
            f"Failed to handle Razorpay subscription cancellation",
            extra={"error": str(e)}
        )


async def _handle_razorpay_subscription_updated(payload: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Handle Razorpay subscription update"""
    try:
        subscription = payload.get("subscription", {}).get("entity", {})
        
        customer_id = subscription.get("customer_id")
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        
        user_id = f"user_{customer_id}"  # Placeholder
        
        logger.info(
            f"Razorpay subscription updated",
            extra={
                "user_id": user_id,
                "subscription_id": subscription_id,
                "status": status
            }
        )
        
        # TODO: Update subscription status in database
        
    except Exception as e:
        logger.error(
            f"Failed to handle Razorpay subscription update",
            extra={"error": str(e)}
        )


# Signature Verification

def _verify_stripe_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Stripe webhook signature
    
    Args:
        payload: Raw request body
        signature: Stripe-Signature header value
        
    Returns:
        True if signature is valid
    """
    try:
        # TODO: Implement actual Stripe signature verification
        # webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        # expected_sig = hmac.new(
        #     webhook_secret.encode(),
        #     payload,
        #     hashlib.sha256
        # ).hexdigest()
        # return hmac.compare_digest(expected_sig, signature)
        return True  # Placeholder
    except Exception as e:
        logger.error(f"Stripe signature verification failed: {str(e)}")
        return False


def _verify_razorpay_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature
    
    Args:
        payload: Raw request body
        signature: X-Razorpay-Signature header value
        
    Returns:
        True if signature is valid
    """
    try:
        # TODO: Implement actual Razorpay signature verification
        # webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        # expected_sig = hmac.new(
        #     webhook_secret.encode(),
        #     payload,
        #     hashlib.sha256
        # ).hexdigest()
        # return hmac.compare_digest(expected_sig, signature)
        return True  # Placeholder
    except Exception as e:
        logger.error(f"Razorpay signature verification failed: {str(e)}")
        return False
