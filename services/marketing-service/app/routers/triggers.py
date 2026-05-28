"""
Behavioral Trigger Router
Exposes endpoints for firing behavioral trigger emails
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from app.services.trigger_service import trigger_service, TriggerType

logger = logging.getLogger(__name__)

router = APIRouter()


# Request Models

class IncompleteOnboardingTriggerRequest(BaseModel):
    """Request to fire incomplete onboarding trigger"""
    user_id: str
    email: EmailStr
    first_name: str
    onboarding_progress: int
    next_step: str
    signup_time: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "first_name": "Rajesh",
                "onboarding_progress": 40,
                "next_step": "Add instruments to watchlist",
                "signup_time": "2024-01-15T10:30:00Z"
            }
        }


class InactiveUserTriggerRequest(BaseModel):
    """Request to fire inactive user trigger"""
    user_id: str
    email: EmailStr
    first_name: str
    last_login: datetime
    days_inactive: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "first_name": "Rajesh",
                "last_login": "2024-01-08T14:20:00Z",
                "days_inactive": 7
            }
        }


class FeatureUnusedTriggerRequest(BaseModel):
    """Request to fire feature unused trigger"""
    user_id: str
    email: EmailStr
    first_name: str
    feature_name: str
    feature_description: str
    days_since_signup: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "first_name": "Rajesh",
                "feature_name": "Options Intelligence",
                "feature_description": "AI-powered options analysis with Greeks and IV insights",
                "days_since_signup": 5
            }
        }


class UpgradePromptTriggerRequest(BaseModel):
    """Request to fire upgrade prompt trigger"""
    user_id: str
    email: EmailStr
    first_name: str
    current_tier: str
    usage_percentage: int
    analyses_used: int
    analyses_limit: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "first_name": "Rajesh",
                "current_tier": "free",
                "usage_percentage": 85,
                "analyses_used": 77,
                "analyses_limit": 90
            }
        }


class FireTriggerRequest(BaseModel):
    """Generic trigger fire request"""
    trigger_type: str
    user_id: str
    email: EmailStr
    context: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "trigger_type": "incomplete_onboarding",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "trader@example.com",
                "context": {
                    "first_name": "Rajesh",
                    "onboarding_progress": 40,
                    "next_step": "Add instruments to watchlist",
                    "signup_time": "2024-01-15T10:30:00Z"
                }
            }
        }


# Endpoints

@router.post("/fire")
async def fire_trigger(request: FireTriggerRequest) -> Dict[str, Any]:
    """
    Fire a behavioral trigger email
    
    Generic endpoint that routes to specific trigger handlers based on trigger_type.
    Consumed by analytics-service webhooks and other internal services.
    
    Supported trigger types:
    - incomplete_onboarding: 24h after signup if onboarding not complete
    - inactive_user: 7 days of no login activity
    - feature_unused: Key feature not used after reasonable time
    - upgrade_prompt: High usage on free tier
    
    Args:
        request: Trigger request with type, user info, and context
        
    Returns:
        Dict with trigger status and job details
        
    Raises:
        HTTPException: If trigger type unknown or firing fails
    """
    try:
        trigger_type = request.trigger_type.lower()
        
        # Route to appropriate trigger handler
        if trigger_type == TriggerType.INCOMPLETE_ONBOARDING:
            result = trigger_service.fire_incomplete_onboarding_trigger(
                user_id=request.user_id,
                email=request.email,
                first_name=request.context.get("first_name", "there"),
                onboarding_progress=request.context.get("onboarding_progress", 0),
                next_step=request.context.get("next_step", "Complete your profile"),
                signup_time=datetime.fromisoformat(request.context.get("signup_time"))
            )
        
        elif trigger_type == TriggerType.INACTIVE_USER:
            result = trigger_service.fire_inactive_user_trigger(
                user_id=request.user_id,
                email=request.email,
                first_name=request.context.get("first_name", "there"),
                last_login=datetime.fromisoformat(request.context.get("last_login")),
                days_inactive=request.context.get("days_inactive", 7)
            )
        
        elif trigger_type == TriggerType.FEATURE_UNUSED:
            result = trigger_service.fire_feature_unused_trigger(
                user_id=request.user_id,
                email=request.email,
                first_name=request.context.get("first_name", "there"),
                feature_name=request.context.get("feature_name", ""),
                feature_description=request.context.get("feature_description", ""),
                days_since_signup=request.context.get("days_since_signup", 0)
            )
        
        elif trigger_type == TriggerType.UPGRADE_PROMPT:
            result = trigger_service.fire_upgrade_prompt_trigger(
                user_id=request.user_id,
                email=request.email,
                first_name=request.context.get("first_name", "there"),
                current_tier=request.context.get("current_tier", "free"),
                usage_percentage=request.context.get("usage_percentage", 0),
                analyses_used=request.context.get("analyses_used", 0),
                analyses_limit=request.context.get("analyses_limit", 90)
            )
        
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown trigger type: {trigger_type}"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to fire trigger",
            extra={
                "trigger_type": request.trigger_type,
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fire trigger: {str(e)}"
        )


@router.post("/incomplete-onboarding")
async def fire_incomplete_onboarding(
    request: IncompleteOnboardingTriggerRequest
) -> Dict[str, Any]:
    """
    Fire incomplete onboarding trigger
    
    Convenience endpoint for incomplete onboarding trigger.
    
    Args:
        request: Incomplete onboarding trigger request
        
    Returns:
        Dict with trigger status
    """
    return trigger_service.fire_incomplete_onboarding_trigger(
        user_id=request.user_id,
        email=request.email,
        first_name=request.first_name,
        onboarding_progress=request.onboarding_progress,
        next_step=request.next_step,
        signup_time=request.signup_time
    )


@router.post("/inactive-user")
async def fire_inactive_user(
    request: InactiveUserTriggerRequest
) -> Dict[str, Any]:
    """
    Fire inactive user trigger
    
    Convenience endpoint for inactive user trigger.
    
    Args:
        request: Inactive user trigger request
        
    Returns:
        Dict with trigger status
    """
    return trigger_service.fire_inactive_user_trigger(
        user_id=request.user_id,
        email=request.email,
        first_name=request.first_name,
        last_login=request.last_login,
        days_inactive=request.days_inactive
    )


@router.post("/feature-unused")
async def fire_feature_unused(
    request: FeatureUnusedTriggerRequest
) -> Dict[str, Any]:
    """
    Fire feature unused trigger
    
    Convenience endpoint for feature unused trigger.
    
    Args:
        request: Feature unused trigger request
        
    Returns:
        Dict with trigger status
    """
    return trigger_service.fire_feature_unused_trigger(
        user_id=request.user_id,
        email=request.email,
        first_name=request.first_name,
        feature_name=request.feature_name,
        feature_description=request.feature_description,
        days_since_signup=request.days_since_signup
    )


@router.post("/upgrade-prompt")
async def fire_upgrade_prompt(
    request: UpgradePromptTriggerRequest
) -> Dict[str, Any]:
    """
    Fire upgrade prompt trigger
    
    Convenience endpoint for upgrade prompt trigger.
    
    Args:
        request: Upgrade prompt trigger request
        
    Returns:
        Dict with trigger status
    """
    return trigger_service.fire_upgrade_prompt_trigger(
        user_id=request.user_id,
        email=request.email,
        first_name=request.first_name,
        current_tier=request.current_tier,
        usage_percentage=request.usage_percentage,
        analyses_used=request.analyses_used,
        analyses_limit=request.analyses_limit
    )
