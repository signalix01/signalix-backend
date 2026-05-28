"""
Referral Program Router
Handles referral link generation, tracking, and stats
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, UUID4
from typing import Optional
import logging
import secrets
import string
from datetime import datetime

from app.config import settings
from app.services.reward_service import reward_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class GenerateReferralLinkRequest(BaseModel):
    """Request to generate a referral link"""
    user_id: UUID4


class GenerateReferralLinkResponse(BaseModel):
    """Response with referral code and link"""
    referral_code: str
    referral_link: str


class ReferralStats(BaseModel):
    """Referral statistics for a user"""
    referral_code: str
    referrals_sent: int
    referrals_signed_up: int
    referrals_converted: int
    rewards_earned_paise: int
    rewards_pending_paise: int


class TrackReferralRequest(BaseModel):
    """Request to track a referral event"""
    referral_code: str
    referred_user_id: UUID4
    event: str  # 'signup', 'activation', 'conversion'


class TrackReferralResponse(BaseModel):
    """Response for referral tracking"""
    success: bool
    message: str


# ============================================================================
# Helper Functions
# ============================================================================

def generate_unique_code(length: int = 8) -> str:
    """
    Generate a unique alphanumeric referral code
    
    Args:
        length: Length of the code (default 8)
        
    Returns:
        Unique referral code
    """
    # Use uppercase letters and digits, excluding ambiguous characters (0, O, I, 1)
    alphabet = string.ascii_uppercase.replace('O', '').replace('I', '') + string.digits.replace('0', '').replace('1', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def get_db_connection():
    """Get database connection (placeholder - implement based on your DB setup)"""
    # This should return your actual database connection
    # For now, we'll use a placeholder
    import asyncpg
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection failed")


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/generate", response_model=GenerateReferralLinkResponse)
async def generate_referral_link(request: GenerateReferralLinkRequest):
    """
    Generate a unique referral link for a user
    
    If the user already has a referral code, return the existing one.
    Otherwise, generate a new unique code.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Check if user already has a referral code
            existing = await conn.fetchrow(
                "SELECT referral_code FROM referrers WHERE user_id = $1",
                str(request.user_id)
            )
            
            if existing:
                referral_code = existing['referral_code']
                logger.info(f"Returning existing referral code for user {request.user_id}")
            else:
                # Generate unique code
                max_attempts = 10
                for attempt in range(max_attempts):
                    referral_code = generate_unique_code(8)
                    
                    # Check if code already exists
                    exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM referrers WHERE referral_code = $1)",
                        referral_code
                    )
                    
                    if not exists:
                        break
                    
                    if attempt == max_attempts - 1:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to generate unique referral code"
                        )
                
                # Insert new referrer
                await conn.execute(
                    """
                    INSERT INTO referrers (user_id, referral_code, total_referrals, successful_referrals, total_rewards_paise)
                    VALUES ($1, $2, 0, 0, 0)
                    """,
                    str(request.user_id),
                    referral_code
                )
                
                logger.info(f"Generated new referral code {referral_code} for user {request.user_id}")
            
            # Construct referral link
            base_url = settings.FRONTEND_URL or "https://signalixai.com"
            referral_link = f"{base_url}/signup?ref={referral_code}"
            
            return GenerateReferralLinkResponse(
                referral_code=referral_code,
                referral_link=referral_link
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating referral link: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate referral link: {str(e)}")


@router.get("/stats/{user_id}", response_model=ReferralStats)
async def get_referral_stats(user_id: UUID4):
    """
    Get referral statistics for a user
    
    Returns:
        - referral_code: User's referral code
        - referrals_sent: Total referrals sent (clicked link)
        - referrals_signed_up: Referrals who signed up
        - referrals_converted: Referrals who became paying customers
        - rewards_earned_paise: Total rewards earned in paise
        - rewards_pending_paise: Pending rewards in paise
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get referrer data
            referrer = await conn.fetchrow(
                """
                SELECT 
                    referral_code,
                    total_referrals,
                    successful_referrals,
                    pending_referrals,
                    total_rewards_paise,
                    pending_rewards_paise
                FROM referrers
                WHERE user_id = $1
                """,
                str(user_id)
            )
            
            if not referrer:
                raise HTTPException(status_code=404, detail="Referral code not found for user")
            
            # Count referrals by status
            referral_counts = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE signup_at IS NOT NULL) as signed_up,
                    COUNT(*) FILTER (WHERE converted_at IS NOT NULL) as converted
                FROM referrals
                WHERE referrer_id = (SELECT id FROM referrers WHERE user_id = $1)
                """,
                str(user_id)
            )
            
            return ReferralStats(
                referral_code=referrer['referral_code'],
                referrals_sent=referrer['total_referrals'],
                referrals_signed_up=referral_counts['signed_up'] or 0,
                referrals_converted=referral_counts['converted'] or 0,
                rewards_earned_paise=referrer['total_rewards_paise'],
                rewards_pending_paise=referrer['pending_rewards_paise']
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching referral stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch referral stats: {str(e)}")


@router.post("/track", response_model=TrackReferralResponse)
async def track_referral(request: TrackReferralRequest):
    """
    Track a referral event (signup, activation, conversion)
    
    Events:
        - signup: Referred user completed signup
        - activation: Referred user completed activation (first analysis)
        - conversion: Referred user became a paying customer
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get referrer
            referrer = await conn.fetchrow(
                "SELECT id FROM referrers WHERE referral_code = $1",
                request.referral_code
            )
            
            if not referrer:
                raise HTTPException(status_code=404, detail="Referral code not found")
            
            referrer_id = referrer['id']
            
            # Check if referral already exists
            existing = await conn.fetchrow(
                """
                SELECT id, status, signup_at, activated_at, converted_at
                FROM referrals
                WHERE referrer_id = $1 AND referred_user_id = $2
                """,
                referrer_id,
                str(request.referred_user_id)
            )
            
            if not existing:
                # Create new referral
                await conn.execute(
                    """
                    INSERT INTO referrals (referrer_id, referred_user_id, status, signup_at)
                    VALUES ($1, $2, 'pending', $3)
                    """,
                    referrer_id,
                    str(request.referred_user_id),
                    datetime.utcnow() if request.event == 'signup' else None
                )
                
                # Increment total_referrals
                await conn.execute(
                    "UPDATE referrers SET total_referrals = total_referrals + 1 WHERE id = $1",
                    referrer_id
                )
                
                logger.info(f"Created new referral for code {request.referral_code}")
            else:
                # Update existing referral based on event
                if request.event == 'signup' and not existing['signup_at']:
                    await conn.execute(
                        "UPDATE referrals SET signup_at = $1 WHERE id = $2",
                        datetime.utcnow(),
                        existing['id']
                    )
                elif request.event == 'activation' and not existing['activated_at']:
                    await conn.execute(
                        "UPDATE referrals SET activated_at = $1 WHERE id = $2",
                        datetime.utcnow(),
                        existing['id']
                    )
                elif request.event == 'conversion' and not existing['converted_at']:
                    await conn.execute(
                        """
                        UPDATE referrals 
                        SET converted_at = $1, status = 'completed'
                        WHERE id = $2
                        """,
                        datetime.utcnow(),
                        existing['id']
                    )
                    
                    # Increment successful_referrals
                    await conn.execute(
                        "UPDATE referrers SET successful_referrals = successful_referrals + 1 WHERE id = $1",
                        referrer_id
                    )
                    
                    # Award rewards for successful conversion
                    referrer_user_id = await conn.fetchval(
                        "SELECT user_id FROM referrers WHERE id = $1",
                        referrer_id
                    )
                    
                    try:
                        await reward_service.award_referral_rewards(
                            referrer_user_id=str(referrer_user_id),
                            referred_user_id=str(request.referred_user_id),
                            referral_id=str(existing['id']),
                            conn=conn
                        )
                    except Exception as e:
                        logger.error(f"Failed to award rewards: {str(e)}")
                        # Don't fail the tracking if reward granting fails
                    
                    logger.info(f"Referral converted for code {request.referral_code}")
            
            return TrackReferralResponse(
                success=True,
                message=f"Referral {request.event} tracked successfully"
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking referral: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to track referral: {str(e)}")


@router.get("/code/{referral_code}")
async def validate_referral_code(referral_code: str):
    """
    Validate a referral code and return referrer info
    
    Used when a user visits a referral link to validate the code
    """
    try:
        conn = await get_db_connection()
        
        try:
            referrer = await conn.fetchrow(
                """
                SELECT 
                    r.user_id,
                    r.referral_code,
                    r.status
                FROM referrers r
                WHERE r.referral_code = $1 AND r.status = 'active'
                """,
                referral_code
            )
            
            if not referrer:
                raise HTTPException(status_code=404, detail="Invalid or inactive referral code")
            
            return {
                "valid": True,
                "referral_code": referrer['referral_code'],
                "referrer_user_id": str(referrer['user_id'])
            }
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating referral code: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to validate referral code: {str(e)}")
