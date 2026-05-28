"""
Affiliate Program Router
Handles affiliate registration, tracking, stats, and commission management
Task: 30.1 - Implement affiliate dashboard backend
Requirements: 12.7, 12.8
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr, UUID4, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
import logging
import secrets
import string

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class AffiliateRegistrationRequest(BaseModel):
    """Request to register as an affiliate"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=255)
    user_id: Optional[UUID4] = None  # If affiliate is also a user
    payment_method: Optional[str] = Field(None, description="bank_transfer, paypal, upi")
    payment_details: Optional[dict] = Field(default_factory=dict)
    notes: Optional[str] = None


class AffiliateRegistrationResponse(BaseModel):
    """Response after affiliate registration"""
    success: bool
    affiliate_id: UUID4
    affiliate_code: str
    status: str
    message: str


class AffiliateStats(BaseModel):
    """Affiliate statistics"""
    affiliate_id: UUID4
    affiliate_code: str
    name: str
    email: str
    status: str
    commission_rate: Decimal
    total_clicks: int
    total_signups: int
    total_conversions: int
    total_commission_paise: int
    pending_commission_paise: int
    paid_commission_paise: int
    created_at: datetime


class AffiliateCommissionRecord(BaseModel):
    """Individual commission record"""
    id: UUID4
    referred_user_id: UUID4
    subscription_id: UUID4
    commission_amount_paise: int
    commission_rate: Decimal
    subscription_amount_paise: int
    period: int
    status: str
    payment_date: Optional[datetime]
    created_at: datetime


class AffiliateCommissionHistory(BaseModel):
    """Commission history response"""
    total_count: int
    commissions: List[AffiliateCommissionRecord]


class AffiliateConversionRecord(BaseModel):
    """Conversion tracking record"""
    id: UUID4
    referred_user_id: UUID4
    subscription_id: Optional[UUID4]
    status: str
    signup_at: Optional[datetime]
    first_payment_at: Optional[datetime]
    total_commission_paise: int
    paid_commission_paise: int
    created_at: datetime


class AffiliatePayoutRecord(BaseModel):
    """Payout record"""
    id: UUID4
    amount_paise: int
    commission_count: int
    payment_method: str
    payment_reference: Optional[str]
    status: str
    scheduled_date: Optional[date]
    processed_at: Optional[datetime]
    created_at: datetime


class AffiliateResource(BaseModel):
    """Marketing resource"""
    id: UUID4
    title: str
    description: Optional[str]
    resource_type: str
    file_url: Optional[str]
    thumbnail_url: Optional[str]
    dimensions: Optional[str]
    format: Optional[str]


class TrackAffiliateClickRequest(BaseModel):
    """Request to track affiliate link click"""
    affiliate_code: str
    visitor_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    referrer_url: Optional[str] = None
    landing_page: Optional[str] = None
    utm_params: Optional[dict] = Field(default_factory=dict)


class TrackAffiliateConversionRequest(BaseModel):
    """Request to track affiliate conversion"""
    affiliate_code: str
    referred_user_id: UUID4
    subscription_id: Optional[UUID4] = None
    event: str = Field(..., description="signup, first_payment, cancelled")


class RecordCommissionRequest(BaseModel):
    """Request to record a commission"""
    affiliate_id: UUID4
    conversion_id: UUID4
    referred_user_id: UUID4
    subscription_id: UUID4
    payment_id: str
    subscription_amount_paise: int
    period: int = Field(..., ge=1, le=12, description="Month number (1-12)")


# ============================================================================
# Helper Functions
# ============================================================================

def generate_affiliate_code(length: int = 10) -> str:
    """
    Generate a unique alphanumeric affiliate code
    
    Args:
        length: Length of the code (default 10)
        
    Returns:
        Unique affiliate code
    """
    # Use uppercase letters and digits, excluding ambiguous characters
    alphabet = string.ascii_uppercase.replace('O', '').replace('I', '') + string.digits.replace('0', '').replace('1', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def get_db_connection():
    """Get database connection"""
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

@router.post("/register", response_model=AffiliateRegistrationResponse)
async def register_affiliate(request: AffiliateRegistrationRequest):
    """
    Register a new affiliate
    
    Creates a new affiliate account with pending status.
    Admin approval required before affiliate can start earning commissions.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Check if email already registered
            existing = await conn.fetchrow(
                "SELECT id, status FROM affiliates WHERE email = $1",
                request.email
            )
            
            if existing:
                if existing['status'] == 'pending':
                    raise HTTPException(
                        status_code=400,
                        detail="Affiliate application already pending approval"
                    )
                elif existing['status'] == 'active':
                    raise HTTPException(
                        status_code=400,
                        detail="Email already registered as active affiliate"
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Affiliate account exists with status: {existing['status']}"
                    )
            
            # Generate unique affiliate code
            max_attempts = 10
            for attempt in range(max_attempts):
                affiliate_code = generate_affiliate_code(10)
                
                # Check if code already exists
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM affiliates WHERE affiliate_code = $1)",
                    affiliate_code
                )
                
                if not exists:
                    break
                
                if attempt == max_attempts - 1:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to generate unique affiliate code"
                    )
            
            # Insert new affiliate
            affiliate_id = await conn.fetchval(
                """
                INSERT INTO affiliates (
                    user_id, email, name, affiliate_code, 
                    payment_method, payment_details, notes, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                RETURNING id
                """,
                str(request.user_id) if request.user_id else None,
                request.email,
                request.name,
                affiliate_code,
                request.payment_method,
                request.payment_details,
                request.notes
            )
            
            logger.info(f"New affiliate registered: {affiliate_code} ({request.email})")
            
            return AffiliateRegistrationResponse(
                success=True,
                affiliate_id=affiliate_id,
                affiliate_code=affiliate_code,
                status="pending",
                message="Affiliate application submitted. Awaiting approval."
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering affiliate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to register affiliate: {str(e)}")


@router.get("/{affiliate_id}/stats", response_model=AffiliateStats)
async def get_affiliate_stats(affiliate_id: UUID4):
    """
    Get comprehensive statistics for an affiliate
    
    Returns:
        - Basic info (name, email, code, status)
        - Click, signup, and conversion counts
        - Commission totals (total, pending, paid)
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get affiliate data
            affiliate = await conn.fetchrow(
                """
                SELECT 
                    id, affiliate_code, name, email, status, commission_rate,
                    total_clicks, total_signups, total_conversions,
                    total_commission_paise, pending_commission_paise, paid_commission_paise,
                    created_at
                FROM affiliates
                WHERE id = $1
                """,
                str(affiliate_id)
            )
            
            if not affiliate:
                raise HTTPException(status_code=404, detail="Affiliate not found")
            
            return AffiliateStats(
                affiliate_id=affiliate['id'],
                affiliate_code=affiliate['affiliate_code'],
                name=affiliate['name'],
                email=affiliate['email'],
                status=affiliate['status'],
                commission_rate=affiliate['commission_rate'],
                total_clicks=affiliate['total_clicks'],
                total_signups=affiliate['total_signups'],
                total_conversions=affiliate['total_conversions'],
                total_commission_paise=affiliate['total_commission_paise'],
                pending_commission_paise=affiliate['pending_commission_paise'],
                paid_commission_paise=affiliate['paid_commission_paise'],
                created_at=affiliate['created_at']
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching affiliate stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch affiliate stats: {str(e)}")


@router.get("/{affiliate_id}/commissions", response_model=AffiliateCommissionHistory)
async def get_affiliate_commissions(
    affiliate_id: UUID4,
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, paid, cancelled"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get commission history for an affiliate
    
    Returns paginated list of commission records with filters.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Build query
            where_clause = "WHERE affiliate_id = $1"
            params = [str(affiliate_id)]
            
            if status:
                where_clause += f" AND status = ${len(params) + 1}"
                params.append(status)
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM affiliate_commissions {where_clause}"
            total_count = await conn.fetchval(count_query, *params)
            
            # Get commissions
            query = f"""
                SELECT 
                    id, referred_user_id, subscription_id,
                    commission_amount_paise, commission_rate, subscription_amount_paise,
                    period, status, payment_date, created_at
                FROM affiliate_commissions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            params.extend([limit, offset])
            
            rows = await conn.fetch(query, *params)
            
            commissions = [
                AffiliateCommissionRecord(
                    id=row['id'],
                    referred_user_id=row['referred_user_id'],
                    subscription_id=row['subscription_id'],
                    commission_amount_paise=row['commission_amount_paise'],
                    commission_rate=row['commission_rate'],
                    subscription_amount_paise=row['subscription_amount_paise'],
                    period=row['period'],
                    status=row['status'],
                    payment_date=row['payment_date'],
                    created_at=row['created_at']
                )
                for row in rows
            ]
            
            return AffiliateCommissionHistory(
                total_count=total_count,
                commissions=commissions
            )
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching affiliate commissions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch commissions: {str(e)}")


@router.get("/{affiliate_id}/conversions")
async def get_affiliate_conversions(
    affiliate_id: UUID4,
    status: Optional[str] = Query(None, description="Filter by status: pending, active, cancelled, completed"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get conversion tracking records for an affiliate
    
    Shows all referred users and their subscription status.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Build query
            where_clause = "WHERE affiliate_id = $1"
            params = [str(affiliate_id)]
            
            if status:
                where_clause += f" AND status = ${len(params) + 1}"
                params.append(status)
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM affiliate_conversions {where_clause}"
            total_count = await conn.fetchval(count_query, *params)
            
            # Get conversions
            query = f"""
                SELECT 
                    id, referred_user_id, subscription_id, status,
                    signup_at, first_payment_at, total_commission_paise,
                    paid_commission_paise, created_at
                FROM affiliate_conversions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            params.extend([limit, offset])
            
            rows = await conn.fetch(query, *params)
            
            conversions = [
                AffiliateConversionRecord(
                    id=row['id'],
                    referred_user_id=row['referred_user_id'],
                    subscription_id=row['subscription_id'],
                    status=row['status'],
                    signup_at=row['signup_at'],
                    first_payment_at=row['first_payment_at'],
                    total_commission_paise=row['total_commission_paise'],
                    paid_commission_paise=row['paid_commission_paise'],
                    created_at=row['created_at']
                )
                for row in rows
            ]
            
            return {
                "total_count": total_count,
                "conversions": conversions
            }
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching affiliate conversions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversions: {str(e)}")


@router.get("/{affiliate_id}/payouts")
async def get_affiliate_payouts(
    affiliate_id: UUID4,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get payout history for an affiliate
    
    Shows all payout batches processed for the affiliate.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get total count
            total_count = await conn.fetchval(
                "SELECT COUNT(*) FROM affiliate_payouts WHERE affiliate_id = $1",
                str(affiliate_id)
            )
            
            # Get payouts
            rows = await conn.fetch(
                """
                SELECT 
                    id, amount_paise, commission_count, payment_method,
                    payment_reference, status, scheduled_date, processed_at, created_at
                FROM affiliate_payouts
                WHERE affiliate_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                str(affiliate_id),
                limit,
                offset
            )
            
            payouts = [
                AffiliatePayoutRecord(
                    id=row['id'],
                    amount_paise=row['amount_paise'],
                    commission_count=row['commission_count'],
                    payment_method=row['payment_method'],
                    payment_reference=row['payment_reference'],
                    status=row['status'],
                    scheduled_date=row['scheduled_date'],
                    processed_at=row['processed_at'],
                    created_at=row['created_at']
                )
                for row in rows
            ]
            
            return {
                "total_count": total_count,
                "payouts": payouts
            }
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching affiliate payouts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch payouts: {str(e)}")


@router.post("/track-click")
async def track_affiliate_click(request: TrackAffiliateClickRequest):
    """
    Track a click on an affiliate link
    
    Records the click and increments affiliate's click count.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get affiliate
            affiliate = await conn.fetchrow(
                "SELECT id, status FROM affiliates WHERE affiliate_code = $1",
                request.affiliate_code
            )
            
            if not affiliate:
                raise HTTPException(status_code=404, detail="Affiliate code not found")
            
            if affiliate['status'] != 'active':
                raise HTTPException(status_code=400, detail="Affiliate is not active")
            
            # Record click
            await conn.execute(
                """
                INSERT INTO affiliate_clicks (
                    affiliate_id, visitor_id, ip_address, user_agent,
                    referrer_url, landing_page, utm_params
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                affiliate['id'],
                request.visitor_id,
                request.ip_address,
                request.user_agent,
                request.referrer_url,
                request.landing_page,
                request.utm_params
            )
            
            # Increment click count
            await conn.execute(
                "UPDATE affiliates SET total_clicks = total_clicks + 1 WHERE id = $1",
                affiliate['id']
            )
            
            logger.info(f"Affiliate click tracked: {request.affiliate_code}")
            
            return {"success": True, "message": "Click tracked"}
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking affiliate click: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to track click: {str(e)}")


@router.post("/track-conversion")
async def track_affiliate_conversion(request: TrackAffiliateConversionRequest):
    """
    Track an affiliate conversion event
    
    Events:
        - signup: Referred user completed signup
        - first_payment: Referred user made first payment
        - cancelled: Referred user cancelled subscription
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get affiliate
            affiliate = await conn.fetchrow(
                "SELECT id, status, commission_rate FROM affiliates WHERE affiliate_code = $1",
                request.affiliate_code
            )
            
            if not affiliate:
                raise HTTPException(status_code=404, detail="Affiliate code not found")
            
            if affiliate['status'] != 'active':
                raise HTTPException(status_code=400, detail="Affiliate is not active")
            
            affiliate_id = affiliate['id']
            
            # Check if conversion already exists
            existing = await conn.fetchrow(
                """
                SELECT id, status, signup_at, first_payment_at
                FROM affiliate_conversions
                WHERE affiliate_id = $1 AND referred_user_id = $2
                """,
                affiliate_id,
                str(request.referred_user_id)
            )
            
            if not existing:
                # Create new conversion
                await conn.execute(
                    """
                    INSERT INTO affiliate_conversions (
                        affiliate_id, referred_user_id, subscription_id, status, signup_at
                    )
                    VALUES ($1, $2, $3, 'pending', $4)
                    """,
                    affiliate_id,
                    str(request.referred_user_id),
                    str(request.subscription_id) if request.subscription_id else None,
                    datetime.utcnow() if request.event == 'signup' else None
                )
                
                # Increment signup count
                if request.event == 'signup':
                    await conn.execute(
                        "UPDATE affiliates SET total_signups = total_signups + 1 WHERE id = $1",
                        affiliate_id
                    )
                
                logger.info(f"New affiliate conversion created: {request.affiliate_code}")
            else:
                # Update existing conversion
                if request.event == 'signup' and not existing['signup_at']:
                    await conn.execute(
                        "UPDATE affiliate_conversions SET signup_at = $1 WHERE id = $2",
                        datetime.utcnow(),
                        existing['id']
                    )
                    await conn.execute(
                        "UPDATE affiliates SET total_signups = total_signups + 1 WHERE id = $1",
                        affiliate_id
                    )
                elif request.event == 'first_payment' and not existing['first_payment_at']:
                    await conn.execute(
                        """
                        UPDATE affiliate_conversions 
                        SET first_payment_at = $1, subscription_id = $2, status = 'active'
                        WHERE id = $3
                        """,
                        datetime.utcnow(),
                        str(request.subscription_id) if request.subscription_id else None,
                        existing['id']
                    )
                    await conn.execute(
                        "UPDATE affiliates SET total_conversions = total_conversions + 1 WHERE id = $1",
                        affiliate_id
                    )
                    logger.info(f"Affiliate conversion activated: {request.affiliate_code}")
                elif request.event == 'cancelled':
                    await conn.execute(
                        "UPDATE affiliate_conversions SET status = 'cancelled', cancelled_at = $1 WHERE id = $2",
                        datetime.utcnow(),
                        existing['id']
                    )
                    logger.info(f"Affiliate conversion cancelled: {request.affiliate_code}")
            
            return {"success": True, "message": f"Conversion {request.event} tracked"}
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking affiliate conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to track conversion: {str(e)}")


@router.post("/record-commission")
async def record_commission(request: RecordCommissionRequest):
    """
    Record a commission for a subscription payment
    
    Called by payment webhook when a referred user's subscription payment succeeds.
    Calculates and records commission based on affiliate's commission rate.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Get affiliate and conversion
            affiliate = await conn.fetchrow(
                "SELECT commission_rate FROM affiliates WHERE id = $1",
                str(request.affiliate_id)
            )
            
            if not affiliate:
                raise HTTPException(status_code=404, detail="Affiliate not found")
            
            conversion = await conn.fetchrow(
                "SELECT status FROM affiliate_conversions WHERE id = $1",
                str(request.conversion_id)
            )
            
            if not conversion:
                raise HTTPException(status_code=404, detail="Conversion not found")
            
            if conversion['status'] not in ['active', 'pending']:
                raise HTTPException(status_code=400, detail="Conversion is not active")
            
            # Check if commission already recorded for this period
            existing = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM affiliate_commissions 
                    WHERE conversion_id = $1 AND period = $2
                )
                """,
                str(request.conversion_id),
                request.period
            )
            
            if existing:
                raise HTTPException(status_code=400, detail="Commission already recorded for this period")
            
            # Calculate commission
            commission_rate = affiliate['commission_rate']
            commission_amount_paise = int(request.subscription_amount_paise * (commission_rate / 100))
            
            # Record commission
            commission_id = await conn.fetchval(
                """
                INSERT INTO affiliate_commissions (
                    affiliate_id, conversion_id, referred_user_id, subscription_id,
                    payment_id, commission_amount_paise, commission_rate,
                    subscription_amount_paise, period, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
                RETURNING id
                """,
                str(request.affiliate_id),
                str(request.conversion_id),
                str(request.referred_user_id),
                str(request.subscription_id),
                request.payment_id,
                commission_amount_paise,
                commission_rate,
                request.subscription_amount_paise,
                request.period
            )
            
            # Update affiliate totals
            await conn.execute(
                """
                UPDATE affiliates 
                SET total_commission_paise = total_commission_paise + $1,
                    pending_commission_paise = pending_commission_paise + $1
                WHERE id = $2
                """,
                commission_amount_paise,
                str(request.affiliate_id)
            )
            
            # Update conversion totals
            await conn.execute(
                """
                UPDATE affiliate_conversions 
                SET total_commission_paise = total_commission_paise + $1
                WHERE id = $2
                """,
                commission_amount_paise,
                str(request.conversion_id)
            )
            
            logger.info(f"Commission recorded: {commission_id} for affiliate {request.affiliate_id}, period {request.period}")
            
            return {
                "success": True,
                "commission_id": commission_id,
                "commission_amount_paise": commission_amount_paise,
                "message": "Commission recorded successfully"
            }
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording commission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to record commission: {str(e)}")


@router.get("/resources", response_model=List[AffiliateResource])
async def get_affiliate_resources(
    resource_type: Optional[str] = Query(None, description="Filter by type: banner, email_template, social_copy, screenshot, video")
):
    """
    Get available marketing resources for affiliates
    
    Returns list of downloadable marketing materials.
    """
    try:
        conn = await get_db_connection()
        
        try:
            # Build query
            where_clause = "WHERE status = 'active'"
            params = []
            
            if resource_type:
                where_clause += f" AND resource_type = ${len(params) + 1}"
                params.append(resource_type)
            
            query = f"""
                SELECT 
                    id, title, description, resource_type, file_url,
                    thumbnail_url, dimensions, format
                FROM affiliate_resources
                {where_clause}
                ORDER BY resource_type, title
            """
            
            rows = await conn.fetch(query, *params)
            
            resources = [
                AffiliateResource(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'],
                    resource_type=row['resource_type'],
                    file_url=row['file_url'],
                    thumbnail_url=row['thumbnail_url'],
                    dimensions=row['dimensions'],
                    format=row['format']
                )
                for row in rows
            ]
            
            return resources
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Error fetching affiliate resources: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch resources: {str(e)}")


@router.get("/code/{affiliate_code}")
async def validate_affiliate_code(affiliate_code: str):
    """
    Validate an affiliate code
    
    Used when a user visits an affiliate link to validate the code.
    """
    try:
        conn = await get_db_connection()
        
        try:
            affiliate = await conn.fetchrow(
                """
                SELECT 
                    id, name, email, status
                FROM affiliates
                WHERE affiliate_code = $1 AND status = 'active'
                """,
                affiliate_code
            )
            
            if not affiliate:
                raise HTTPException(status_code=404, detail="Invalid or inactive affiliate code")
            
            return {
                "valid": True,
                "affiliate_code": affiliate_code,
                "affiliate_id": str(affiliate['id']),
                "affiliate_name": affiliate['name']
            }
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating affiliate code: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to validate affiliate code: {str(e)}")

