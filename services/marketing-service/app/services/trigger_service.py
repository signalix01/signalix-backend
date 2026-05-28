"""
Behavioral Trigger Email Service
Handles trigger-based emails based on user behavior and events
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from rq import Queue

from app.config import settings
from app.tasks.email_tasks import redis_conn, email_queue

logger = logging.getLogger(__name__)


class TriggerType:
    """Supported behavioral trigger types"""
    INCOMPLETE_ONBOARDING = "incomplete_onboarding"
    INACTIVE_USER = "inactive_user"
    FEATURE_UNUSED = "feature_unused"
    UPGRADE_PROMPT = "upgrade_prompt"


class TriggerService:
    """Service for managing behavioral trigger emails"""
    
    def __init__(self):
        self.queue = email_queue
    
    def fire_incomplete_onboarding_trigger(
        self,
        user_id: str,
        email: str,
        first_name: str,
        onboarding_progress: int,
        next_step: str,
        signup_time: datetime
    ) -> Dict[str, Any]:
        """
        Fire incomplete onboarding trigger
        
        Sent 24 hours after signup if user hasn't completed onboarding.
        
        Args:
            user_id: User ID
            email: User email
            first_name: User's first name
            onboarding_progress: Completion percentage (0-100)
            next_step: Description of next onboarding step
            signup_time: When user signed up
            
        Returns:
            Dict with trigger status
        """
        try:
            # Check if 24 hours have passed since signup
            hours_since_signup = (datetime.utcnow() - signup_time).total_seconds() / 3600
            
            if hours_since_signup < 24:
                logger.info(
                    f"Too early for incomplete_onboarding trigger",
                    extra={
                        "user_id": user_id,
                        "hours_since_signup": hours_since_signup
                    }
                )
                return {
                    "success": False,
                    "message": "Too early to send incomplete onboarding email"
                }
            
            # Schedule email for immediate delivery
            context = {
                "first_name": first_name,
                "user_id": user_id,
                "onboarding_progress": onboarding_progress,
                "next_step": next_step,
                "dashboard_url": settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={email}",
            }
            
            job = self.queue.enqueue(
                'app.tasks.email_tasks.send_trigger_email',
                trigger_type=TriggerType.INCOMPLETE_ONBOARDING,
                to_email=email,
                context=context,
                job_id=f"trigger_incomplete_onboarding_{user_id}",
                job_timeout='10m'
            )
            
            logger.info(
                f"Incomplete onboarding trigger fired",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "job_id": job.id
                }
            )
            
            return {
                "success": True,
                "message": "Incomplete onboarding email queued",
                "trigger_type": TriggerType.INCOMPLETE_ONBOARDING,
                "job_id": job.id
            }
            
        except Exception as e:
            logger.error(
                f"Failed to fire incomplete_onboarding trigger",
                extra={
                    "user_id": user_id,
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "message": f"Failed to queue email: {str(e)}"
            }
    
    def fire_inactive_user_trigger(
        self,
        user_id: str,
        email: str,
        first_name: str,
        last_login: datetime,
        days_inactive: int
    ) -> Dict[str, Any]:
        """
        Fire inactive user trigger
        
        Sent after 7 days of no login activity.
        
        Args:
            user_id: User ID
            email: User email
            first_name: User's first name
            last_login: Last login timestamp
            days_inactive: Number of days since last login
            
        Returns:
            Dict with trigger status
        """
        try:
            # Check if user has been inactive for at least 7 days
            if days_inactive < 7:
                logger.info(
                    f"Too early for inactive_user trigger",
                    extra={
                        "user_id": user_id,
                        "days_inactive": days_inactive
                    }
                )
                return {
                    "success": False,
                    "message": "User not inactive long enough"
                }
            
            context = {
                "first_name": first_name,
                "user_id": user_id,
                "days_inactive": days_inactive,
                "last_login": last_login.strftime("%B %d, %Y"),
                "dashboard_url": settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={email}",
            }
            
            job = self.queue.enqueue(
                'app.tasks.email_tasks.send_trigger_email',
                trigger_type=TriggerType.INACTIVE_USER,
                to_email=email,
                context=context,
                job_id=f"trigger_inactive_user_{user_id}",
                job_timeout='10m'
            )
            
            logger.info(
                f"Inactive user trigger fired",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "days_inactive": days_inactive,
                    "job_id": job.id
                }
            )
            
            return {
                "success": True,
                "message": "Inactive user email queued",
                "trigger_type": TriggerType.INACTIVE_USER,
                "job_id": job.id
            }
            
        except Exception as e:
            logger.error(
                f"Failed to fire inactive_user trigger",
                extra={
                    "user_id": user_id,
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "message": f"Failed to queue email: {str(e)}"
            }
    
    def fire_feature_unused_trigger(
        self,
        user_id: str,
        email: str,
        first_name: str,
        feature_name: str,
        feature_description: str,
        days_since_signup: int
    ) -> Dict[str, Any]:
        """
        Fire feature unused trigger
        
        Sent when user hasn't used a key feature after reasonable time.
        
        Args:
            user_id: User ID
            email: User email
            first_name: User's first name
            feature_name: Name of unused feature
            feature_description: Description of the feature
            days_since_signup: Days since user signed up
            
        Returns:
            Dict with trigger status
        """
        try:
            context = {
                "first_name": first_name,
                "user_id": user_id,
                "feature_name": feature_name,
                "feature_description": feature_description,
                "days_since_signup": days_since_signup,
                "dashboard_url": settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={email}",
            }
            
            job = self.queue.enqueue(
                'app.tasks.email_tasks.send_trigger_email',
                trigger_type=TriggerType.FEATURE_UNUSED,
                to_email=email,
                context=context,
                job_id=f"trigger_feature_unused_{user_id}_{feature_name}",
                job_timeout='10m'
            )
            
            logger.info(
                f"Feature unused trigger fired",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "feature": feature_name,
                    "job_id": job.id
                }
            )
            
            return {
                "success": True,
                "message": "Feature unused email queued",
                "trigger_type": TriggerType.FEATURE_UNUSED,
                "job_id": job.id
            }
            
        except Exception as e:
            logger.error(
                f"Failed to fire feature_unused trigger",
                extra={
                    "user_id": user_id,
                    "feature": feature_name,
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "message": f"Failed to queue email: {str(e)}"
            }
    
    def fire_upgrade_prompt_trigger(
        self,
        user_id: str,
        email: str,
        first_name: str,
        current_tier: str,
        usage_percentage: int,
        analyses_used: int,
        analyses_limit: int
    ) -> Dict[str, Any]:
        """
        Fire upgrade prompt trigger
        
        Sent when free tier user has high usage (approaching limit).
        
        Args:
            user_id: User ID
            email: User email
            first_name: User's first name
            current_tier: Current subscription tier
            usage_percentage: Percentage of limit used
            analyses_used: Number of analyses used this period
            analyses_limit: Maximum analyses allowed
            
        Returns:
            Dict with trigger status
        """
        try:
            # Only send to free tier users
            if current_tier.lower() != "free":
                logger.info(
                    f"Skipping upgrade_prompt for non-free user",
                    extra={
                        "user_id": user_id,
                        "tier": current_tier
                    }
                )
                return {
                    "success": False,
                    "message": "User is not on free tier"
                }
            
            # Only send if usage is high (>80%)
            if usage_percentage < 80:
                logger.info(
                    f"Usage too low for upgrade_prompt",
                    extra={
                        "user_id": user_id,
                        "usage_percentage": usage_percentage
                    }
                )
                return {
                    "success": False,
                    "message": "Usage not high enough for upgrade prompt"
                }
            
            context = {
                "first_name": first_name,
                "user_id": user_id,
                "current_tier": current_tier,
                "usage_percentage": usage_percentage,
                "analyses_used": analyses_used,
                "analyses_limit": analyses_limit,
                "analyses_remaining": analyses_limit - analyses_used,
                "pricing_url": f"{settings.DASHBOARD_URL}/pricing",
                "upgrade_url": f"{settings.DASHBOARD_URL}/upgrade",
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email={email}",
            }
            
            job = self.queue.enqueue(
                'app.tasks.email_tasks.send_trigger_email',
                trigger_type=TriggerType.UPGRADE_PROMPT,
                to_email=email,
                context=context,
                job_id=f"trigger_upgrade_prompt_{user_id}",
                job_timeout='10m'
            )
            
            logger.info(
                f"Upgrade prompt trigger fired",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "usage_percentage": usage_percentage,
                    "job_id": job.id
                }
            )
            
            return {
                "success": True,
                "message": "Upgrade prompt email queued",
                "trigger_type": TriggerType.UPGRADE_PROMPT,
                "job_id": job.id
            }
            
        except Exception as e:
            logger.error(
                f"Failed to fire upgrade_prompt trigger",
                extra={
                    "user_id": user_id,
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "message": f"Failed to queue email: {str(e)}"
            }


# Singleton instance
trigger_service = TriggerService()
