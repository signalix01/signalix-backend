"""
Email Service - SendGrid Integration
Handles transactional and marketing email sending with retry logic
"""
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Personalization
from typing import Dict, Any, Optional, List
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sendgrid.helpers.mail import MailSettings, SandBoxMode

from app.config import settings

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Base exception for email service errors"""
    pass


class EmailService:
    """SendGrid email service wrapper with retry logic"""
    
    def __init__(self):
        """Initialize SendGrid client"""
        self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        self.from_email = Email(settings.FROM_EMAIL, settings.FROM_NAME)
        
        # Template ID mapping
        self.templates = {
            "welcome": settings.TEMPLATE_WELCOME,
            "verify_email": settings.TEMPLATE_VERIFY_EMAIL,
            "password_reset": settings.TEMPLATE_PASSWORD_RESET,
            "subscription_confirmation": settings.TEMPLATE_SUBSCRIPTION_CONFIRMATION,
            "payment_receipt": settings.TEMPLATE_PAYMENT_RECEIPT,
            # Onboarding sequence templates
            "getting_started": settings.TEMPLATE_GETTING_STARTED,
            "first_analysis_tips": settings.TEMPLATE_FIRST_ANALYSIS_TIPS,
            "feature_discovery": settings.TEMPLATE_FEATURE_DISCOVERY,
            "success_stories": settings.TEMPLATE_SUCCESS_STORIES,
            "trial_ending": settings.TEMPLATE_TRIAL_ENDING,
            # Behavioral trigger templates
            "incomplete_onboarding": settings.TEMPLATE_INCOMPLETE_ONBOARDING,
            "inactive_user": settings.TEMPLATE_INACTIVE_USER,
            "feature_unused": settings.TEMPLATE_FEATURE_UNUSED,
            "upgrade_prompt": settings.TEMPLATE_UPGRADE_PROMPT,
            # Lead magnet nurture sequence templates
            "lead_magnet_delivery": settings.TEMPLATE_LEAD_MAGNET_DELIVERY,
            "related_content": settings.TEMPLATE_RELATED_CONTENT,
            "case_study": settings.TEMPLATE_CASE_STUDY,
            "trial_invitation": settings.TEMPLATE_TRIAL_INVITATION,
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def send_transactional(
        self,
        template_name: str,
        to_email: str,
        dynamic_data: Dict[str, Any],
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send transactional email using SendGrid dynamic template
        
        Args:
            template_name: Template identifier (e.g., 'welcome', 'verify_email')
            to_email: Recipient email address
            dynamic_data: Template variables (e.g., {'first_name': 'John', 'verification_code': '123456'})
            reply_to: Optional reply-to email address
            
        Returns:
            Dict with success status and message_id
            
        Raises:
            EmailServiceError: If email sending fails after retries
        """
        try:
            # Get template ID
            template_id = self.templates.get(template_name)
            if not template_id:
                raise EmailServiceError(f"Unknown template: {template_name}")
            
            # Build message
            message = Mail(
                from_email=self.from_email,
                to_emails=To(to_email)
            )
            message.template_id = template_id
            message.dynamic_template_data = dynamic_data
            
            # Add reply-to if provided
            if reply_to:
                message.reply_to = Email(reply_to)
            elif settings.REPLY_TO_EMAIL:
                message.reply_to = Email(settings.REPLY_TO_EMAIL)
            
            # Send email
            response = self.client.send(message)
            
            # Log success
            logger.info(
                f"Transactional email sent successfully",
                extra={
                    "template": template_name,
                    "to_email": to_email,
                    "status_code": response.status_code,
                    "message_id": response.headers.get('X-Message-Id')
                }
            )
            
            return {
                "success": True,
                "message_id": response.headers.get('X-Message-Id'),
                "status_code": response.status_code
            }
            
        except Exception as e:
            logger.error(
                f"Failed to send transactional email",
                extra={
                    "template": template_name,
                    "to_email": to_email,
                    "error": str(e)
                }
            )
            raise EmailServiceError(f"Failed to send email: {str(e)}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def send_marketing(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        plain_content: str,
        unsubscribe_group_id: Optional[int] = None,
        custom_args: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send marketing email to multiple recipients
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject line
            html_content: HTML email body
            plain_content: Plain text email body (fallback)
            unsubscribe_group_id: SendGrid unsubscribe group ID
            custom_args: Custom tracking arguments
            
        Returns:
            Dict with success status and recipient count
            
        Raises:
            EmailServiceError: If email sending fails after retries
        """
        try:
            # Build message
            message = Mail(
                from_email=self.from_email,
                subject=subject
            )
            
            # Add content
            message.content = [
                Content("text/plain", plain_content),
                Content("text/html", html_content)
            ]
            
            # Add recipients
            personalization = Personalization()
            for email in to_emails:
                personalization.add_to(To(email))
            message.add_personalization(personalization)
            
            # Add unsubscribe group if provided
            if unsubscribe_group_id:
                message.asm = {
                    "group_id": unsubscribe_group_id
                }
            
            # Add custom tracking args
            if custom_args:
                message.custom_args = custom_args
            
            # Send email
            response = self.client.send(message)
            
            # Log success
            logger.info(
                f"Marketing email sent successfully",
                extra={
                    "subject": subject,
                    "recipient_count": len(to_emails),
                    "status_code": response.status_code
                }
            )
            
            return {
                "success": True,
                "recipients": len(to_emails),
                "status_code": response.status_code
            }
            
        except Exception as e:
            logger.error(
                f"Failed to send marketing email",
                extra={
                    "subject": subject,
                    "recipient_count": len(to_emails),
                    "error": str(e)
                }
            )
            raise EmailServiceError(f"Failed to send marketing email: {str(e)}")
    
    def get_template_id(self, template_name: str) -> Optional[str]:
        """Get SendGrid template ID by name"""
        return self.templates.get(template_name)


# Singleton instance
email_service = EmailService()
