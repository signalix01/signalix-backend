"""
User Context System

Provides user profile context injection for LLM prompts.
"""

from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """User profile and preferences for LLM prompt personalization."""
    user_id: str = Field(..., description="User UUID")
    language: str = Field("en")
    risk_tolerance: int = Field(5, ge=1, le=10)
    capital_inr: float = Field(100000.0, ge=0)
    trading_style: str = Field("swing")
    preferred_instruments: List[str] = Field(default_factory=list)
    preferred_asset_classes: List[str] = Field(default_factory=list)
    tier: str = Field("basic")
    experience_level: str = Field("intermediate")
    analysis_depth: str = Field("shallow")
    notifications_enabled: bool = Field(True)


class UserContextInjector:
    """Builds personalized context strings for LLM prompt injection."""

    STYLE_MAP = {
        "intraday": "an intraday trader needing quick, actionable signals",
        "swing": "a swing trader holding 3-14 days, looking for momentum",
        "positional": "a positional trader holding weeks to months",
        "long_term": "a long-term investor focused on fundamentals",
    }

    def build_context(self, user: UserContext) -> str:
        style = self.STYLE_MAP.get(user.trading_style, f"a {user.trading_style} trader")
        if user.risk_tolerance <= 3:
            risk = "conservative"
        elif user.risk_tolerance <= 6:
            risk = "moderate"
        elif user.risk_tolerance <= 8:
            risk = "aggressive"
        else:
            risk = "very aggressive"

        lines = [
            f"User Profile: {style}",
            f"Risk Tolerance: {user.risk_tolerance}/10 ({risk})",
            f"Capital: ₹{user.capital_inr:,.0f}",
            f"Experience: {user.experience_level}",
            f"Tier: {user.tier}",
            f"Depth: {user.analysis_depth}",
            f"Language: {user.language}",
        ]
        if user.preferred_instruments:
            lines.append(f"Instruments: {', '.join(user.preferred_instruments)}")
        return "\n".join(lines)

    def build_context_from_dict(self, data: dict) -> str:
        return self.build_context(UserContext(**data))
        
    def inject_for_fundamentals_agent(self, user: UserContext) -> str:
        return self.build_context(user)
        
    def inject_for_technical_agent(self, user: UserContext) -> str:
        return self.build_context(user)
        
    def inject_for_macro_agent(self, user: UserContext) -> str:
        return self.build_context(user)
        
    def inject_for_sentiment_agent(self, user: UserContext) -> str:
        return self.build_context(user)
        
    def inject_for_risk_manager(self, user: UserContext) -> str:
        return self.build_context(user)
        
    def inject_for_final_trader(self, user: UserContext) -> str:
        return self.build_context(user)
