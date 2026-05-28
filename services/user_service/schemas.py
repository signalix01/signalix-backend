from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str
    declared_trading_capital_inr: float
    risk_tolerance_score: int
    investment_horizon: Literal['intraday', 'swing', 'positional', 'long-term']

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False

class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: str
    country_of_residence: str
    risk_tolerance_score: int
    investment_horizon: str
    declared_trading_capital_inr: float
    email_verified: bool
    phone_verified: bool
    sebi_declaration_acknowledged: bool
    created_at: datetime

    class Config:
        from_attributes = True

class AuthTokensResponse(BaseModel):
    access_token: str
    user: UserResponse
