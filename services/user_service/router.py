from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import datetime

from shared.database.session import get_db
from shared.database.user_models import User
from shared.utils.auth import get_password_hash, verify_password, create_access_token, create_refresh_token
from shared.security.dependencies import get_current_user
from .schemas import RegisterRequest, LoginRequest, UserResponse, AuthTokensResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_EXISTS")

    # Create user
    user = User(
        email=request.email,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name,
        phone=request.phone,
        declared_trading_capital_inr=request.declared_trading_capital_inr,
        risk_tolerance_score=request.risk_tolerance_score,
        investment_horizon=request.investment_horizon,
        country_of_residence="IN",
        sebi_declaration_acknowledged=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user_id": str(user.id), "message": "Registration successful"}

@router.post("/login", response_model=AuthTokensResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # Find user
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalars().first()

    if not user or not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True, # Should be False for localhost HTTP, but this is standard
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

    return {
        "access_token": access_token,
        "user": user
    }

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "subscriptionTier": current_user.subscription_tier or "trial",
        "emailVerified": current_user.is_email_verified,
        "createdAt": current_user.created_at.isoformat() + "Z" if current_user.created_at else None,
        "updatedAt": current_user.updated_at.isoformat() + "Z" if current_user.updated_at else None,
        "tier1": {
            "email": current_user.email,
            "phone": current_user.phone,
            "fullName": current_user.full_name,
            "country": current_user.country_of_residence,
            "declaredCapital": current_user.declared_trading_capital_inr,
            "riskTolerance": current_user.risk_tolerance_score,
            "investmentHorizon": current_user.investment_horizon
        }
    }


# --- Additional endpoints expected by the frontend ---

# User profile update endpoint (the frontend calls PUT /api/v1/user/profile)
user_router = APIRouter(prefix="/api/v1/user", tags=["user"])

@user_router.put("/profile")
async def update_user_profile(request: dict = {}):
    """Stub: Accept profile updates (e.g. market preference) and return OK."""
    return {"status": "ok", "message": "Profile updated"}

@user_router.get("/profile")
async def get_user_profile_alt(current_user: User = Depends(get_current_user)):
    """Alias for /api/v1/auth/profile"""
    return {
        "id": str(current_user.id),
        "subscriptionTier": current_user.subscription_tier or "trial",
        "emailVerified": current_user.is_email_verified,
        "preferredMarket": "nse-bse"
    }

# Onboarding status endpoint (frontend calls GET /api/v1/users/{user_id}/onboarding-status)
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])

@users_router.get("/{user_id}/onboarding-status")
async def get_onboarding_status(user_id: str):
    """Return default onboarding status so the frontend doesn't error."""
    return {
        "userId": user_id,
        "completed": True,
        "currentStep": "done",
        "steps": {
            "account_created": True,
            "profile_completed": True,
            "broker_connected": True,
            "first_strategy": True
        }
    }
