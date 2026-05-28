"""
Email Tasks - Async email sending via RQ (Redis Queue)
"""
from typing import Dict, Any, Optional, List
import logging
from rq import Queue
from redis import Redis

from app.config import settings
from app.services.email_service import email_service, EmailServiceError

logger = logging.getLogger(__name__)

# Initialize Redis connection for RQ
redis_conn = Redis.from_url(settings.REDIS_URL)
email_queue = Queue('emails', connection=redis_conn)


# Transactional Email Tasks

def send_welcome_email(
    to_email: str,
    first_name: str,
    dashboard_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send welcome email to new user
    
    Args:
        to_email: Recipient email
        first_name: User's first name
        dashboard_url: Custom dashboard URL (optional)
    """
    try:
        result = email_service.send_transactional(
            template_name="welcome",
            to_email=to_email,
            dynamic_data={
                "first_name": first_name,
                "dashboard_url": dashboard_url or settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={to_email}",
                "preferences_url": f"{settings.PREFERENCES_BASE_URL}?email={to_email}",
            }
        )
        logger.info(f"Welcome email queued for {to_email}")
        return result
    except EmailServiceError as e:
        logger.error(f"Failed to send welcome email to {to_email}: {str(e)}")
        raise


def send_verification_email(
    to_email: str,
    verification_code: str
) -> Dict[str, Any]:
    """
    Send email verification OTP
    
    Args:
        to_email: Recipient email
        verification_code: 6-digit OTP code
    """
    try:
        result = email_service.send_transactional(
            template_name="verify_email",
            to_email=to_email,
            dynamic_data={
                "verification_code": verification_code,
            }
        )
        logger.info(f"Verification email queued for {to_email}")
        return result
    except EmailServiceError as e:
        logger.error(f"Failed to send verification email to {to_email}: {str(e)}")
        raise


def send_password_reset_email(
    to_email: str,
    reset_token: str,
    first_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send password reset email
    
    Args:
        to_email: Recipient email
        reset_token: Password reset token
        first_name: User's first name (optional)
    """
    try:
        reset_url = f"{settings.DASHBOARD_URL}/reset-password?token={reset_token}"
        
        result = email_service.send_transactional(
            template_name="password_reset",
            to_email=to_email,
            dynamic_data={
                "first_name": first_name or "there",
                "reset_url": reset_url,
                "reset_token": reset_token,
            }
        )
        logger.info(f"Password reset email queued for {to_email}")
        return result
    except EmailServiceError as e:
        logger.error(f"Failed to send password reset email to {to_email}: {str(e)}")
        raise


def send_subscription_confirmation_email(
    to_email: str,
    first_name: str,
    plan_name: str,
    plan_price: float,
    billing_period: str,
    next_billing_date: str
) -> Dict[str, Any]:
    """
    Send subscription confirmation email
    
    Args:
        to_email: Recipient email
        first_name: User's first name
        plan_name: Subscription plan name (Pro, Elite)
        plan_price: Plan price in INR
        billing_period: 'monthly' or 'annual'
        next_billing_date: Next billing date (formatted string)
    """
    try:
        result = email_service.send_transactional(
            template_name="subscription_confirmation",
            to_email=to_email,
            dynamic_data={
                "first_name": first_name,
                "plan_name": plan_name,
                "plan_price": f"₹{plan_price:,.2f}",
                "billing_period": billing_period,
                "next_billing_date": next_billing_date,
                "dashboard_url": settings.DASHBOARD_URL,
                "manage_subscription_url": f"{settings.DASHBOARD_URL}/settings/subscription",
            }
        )
        logger.info(f"Subscription confirmation email queued for {to_email}")
        return result
    except EmailServiceError as e:
        logger.error(f"Failed to send subscription confirmation email to {to_email}: {str(e)}")
        raise


def send_payment_receipt_email(
    to_email: str,
    first_name: str,
    invoice_number: str,
    payment_date: str,
    amount_paid: float,
    plan_name: str,
    billing_period: str,
    payment_method: str
) -> Dict[str, Any]:
    """
    Send payment receipt email
    
    Args:
        to_email: Recipient email
        first_name: User's first name
        invoice_number: Invoice/receipt number
        payment_date: Payment date (formatted string)
        amount_paid: Amount paid in INR
        plan_name: Subscription plan name
        billing_period: 'monthly' or 'annual'
        payment_method: Payment method (e.g., 'Visa ending in 4242')
    """
    try:
        result = email_service.send_transactional(
            template_name="payment_receipt",
            to_email=to_email,
            dynamic_data={
                "first_name": first_name,
                "invoice_number": invoice_number,
                "payment_date": payment_date,
                "amount_paid": f"₹{amount_paid:,.2f}",
                "plan_name": plan_name,
                "billing_period": billing_period,
                "payment_method": payment_method,
                "dashboard_url": settings.DASHBOARD_URL,
                "invoice_url": f"{settings.DASHBOARD_URL}/invoices/{invoice_number}",
            }
        )
        logger.info(f"Payment receipt email queued for {to_email}")
        return result
    except EmailServiceError as e:
        logger.error(f"Failed to send payment receipt email to {to_email}: {str(e)}")
        raise


# Queue helper functions

def queue_welcome_email(to_email: str, first_name: str) -> None:
    """Queue welcome email for async sending"""
    email_queue.enqueue(
        send_welcome_email,
        to_email=to_email,
        first_name=first_name
    )


def queue_verification_email(to_email: str, verification_code: str) -> None:
    """Queue verification email for async sending"""
    email_queue.enqueue(
        send_verification_email,
        to_email=to_email,
        verification_code=verification_code
    )


def queue_password_reset_email(to_email: str, reset_token: str, first_name: Optional[str] = None) -> None:
    """Queue password reset email for async sending"""
    email_queue.enqueue(
        send_password_reset_email,
        to_email=to_email,
        reset_token=reset_token,
        first_name=first_name
    )


def queue_subscription_confirmation_email(
    to_email: str,
    first_name: str,
    plan_name: str,
    plan_price: float,
    billing_period: str,
    next_billing_date: str
) -> None:
    """Queue subscription confirmation email for async sending"""
    email_queue.enqueue(
        send_subscription_confirmation_email,
        to_email=to_email,
        first_name=first_name,
        plan_name=plan_name,
        plan_price=plan_price,
        billing_period=billing_period,
        next_billing_date=next_billing_date
    )


def queue_payment_receipt_email(
    to_email: str,
    first_name: str,
    invoice_number: str,
    payment_date: str,
    amount_paid: float,
    plan_name: str,
    billing_period: str,
    payment_method: str
) -> None:
    """Queue payment receipt email for async sending"""
    email_queue.enqueue(
        send_payment_receipt_email,
        to_email=to_email,
        first_name=first_name,
        invoice_number=invoice_number,
        payment_date=payment_date,
        amount_paid=amount_paid,
        plan_name=plan_name,
        billing_period=billing_period,
        payment_method=payment_method
    )


# Sequence and Trigger Email Tasks

def send_sequence_email(
    to_email: str,
    template_name: str,
    subject: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send email as part of a sequence
    
    Args:
        to_email: Recipient email
        template_name: Email template name
        subject: Email subject line
        context: Template context variables
    """
    try:
        result = email_service.send_transactional(
            template_name=template_name,
            to_email=to_email,
            dynamic_data=context
        )
        
        logger.info(
            f"Sequence email sent",
            extra={
                "to_email": to_email,
                "template": template_name,
                "subject": subject
            }
        )
        
        return result
        
    except EmailServiceError as e:
        logger.error(
            f"Failed to send sequence email",
            extra={
                "to_email": to_email,
                "template": template_name,
                "error": str(e)
            }
        )
        raise


def send_trigger_email(
    trigger_type: str,
    to_email: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send behavioral trigger email
    
    Args:
        trigger_type: Type of trigger (incomplete_onboarding, inactive_user, etc.)
        to_email: Recipient email
        context: Template context variables
    """
    try:
        # Use trigger_type as template name directly
        result = email_service.send_transactional(
            template_name=trigger_type,
            to_email=to_email,
            dynamic_data=context
        )
        
        logger.info(
            f"Trigger email sent",
            extra={
                "to_email": to_email,
                "trigger_type": trigger_type
            }
        )
        
        return result
        
    except EmailServiceError as e:
        logger.error(
            f"Failed to send trigger email",
            extra={
                "to_email": to_email,
                "trigger_type": trigger_type,
                "error": str(e)
            }
        )
        raise
