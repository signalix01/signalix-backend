"""
Pydantic models for screening criteria and results

Requirements: 9.4, 10.1, 10.2, 10.3, 10.4
"""
from pydantic import BaseModel, Field, validator
from typing import List, Literal, Optional
from enum import Enum


class ScreeningCriteria(BaseModel):
    """Flexible screening criteria for any market"""
    name: str = Field(..., description="Name of the screening criteria")
    description: str = Field(..., description="Description of what this screener looks for")
    asset_class: List[str] = Field(..., description="Asset classes to screen: equity, fo, crypto, forex, commodity")
    
    # Fundamental filters (equity only)
    min_market_cap_cr: Optional[float] = Field(None, description="Minimum market cap in crores")
    max_pe_ratio: Optional[float] = Field(None, description="Maximum P/E ratio")
    min_roe_pct: Optional[float] = Field(None, description="Minimum ROE percentage")
    min_revenue_growth_pct: Optional[float] = Field(None, description="Minimum revenue growth percentage")
    min_promoter_holding_pct: Optional[float] = Field(None, description="Minimum promoter holding percentage")
    
    # Technical filters (all markets)
    min_rsi: Optional[float] = Field(None, ge=0, le=100, description="Minimum RSI value")
    max_rsi: Optional[float] = Field(None, ge=0, le=100, description="Maximum RSI value")
    require_above_ema: Optional[int] = Field(None, description="Require price above X-period EMA (e.g., 200)")
    min_adx: Optional[float] = Field(None, ge=0, le=100, description="Minimum ADX for trending instruments")
    min_volume_ratio: Optional[float] = Field(None, gt=0, description="Minimum volume vs 20-day average")
    price_breakout_days: Optional[int] = Field(None, gt=0, description="New X-day high breakout")
    
    # Options-specific (F&O)
    min_iv_rank: Optional[float] = Field(None, ge=0, le=100, description="Minimum IV rank")
    max_iv_rank: Optional[float] = Field(None, ge=0, le=100, description="Maximum IV rank")
    min_pcr: Optional[float] = Field(None, gt=0, description="Minimum Put-Call Ratio")
    max_pcr: Optional[float] = Field(None, gt=0, description="Maximum Put-Call Ratio")
    
    # Crypto-specific
    min_fear_greed: Optional[int] = Field(None, ge=0, le=100, description="Minimum Fear & Greed Index")
    max_funding_rate: Optional[float] = Field(None, description="Maximum funding rate")
    min_on_chain_netflow_btc: Optional[float] = Field(None, description="Minimum on-chain netflow (negative = bullish)")
    
    # AI scoring
    min_ai_confidence: Optional[float] = Field(None, ge=0, le=100, description="Minimum AI confidence score")
    ai_direction_filter: Optional[Literal["BUY", "SELL", "either"]] = Field(None, description="Filter by AI signal direction")
    
    @validator('asset_class')
    def validate_asset_class(cls, v):
        """Validate asset class values"""
        valid_classes = {"equity", "fo", "crypto", "forex", "commodity"}
        for ac in v:
            if ac not in valid_classes:
                raise ValueError(f"Invalid asset class: {ac}. Must be one of {valid_classes}")
        return v
    
    @validator('max_rsi')
    def validate_rsi_range(cls, v, values):
        """Ensure max_rsi > min_rsi if both are set"""
        if v is not None and 'min_rsi' in values and values['min_rsi'] is not None:
            if v <= values['min_rsi']:
                raise ValueError("max_rsi must be greater than min_rsi")
        return v
    
    @validator('max_iv_rank')
    def validate_iv_rank_range(cls, v, values):
        """Ensure max_iv_rank > min_iv_rank if both are set"""
        if v is not None and 'min_iv_rank' in values and values['min_iv_rank'] is not None:
            if v <= values['min_iv_rank']:
                raise ValueError("max_iv_rank must be greater than min_iv_rank")
        return v
    
    @validator('max_pcr')
    def validate_pcr_range(cls, v, values):
        """Ensure max_pcr > min_pcr if both are set"""
        if v is not None and 'min_pcr' in values and values['min_pcr'] is not None:
            if v <= values['min_pcr']:
                raise ValueError("max_pcr must be greater than min_pcr")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Oversold Reversal Scanner",
                "description": "Find oversold stocks with strong fundamentals showing reversal signals",
                "asset_class": ["equity"],
                "min_market_cap_cr": 1000.0,
                "max_pe_ratio": 30.0,
                "min_roe_pct": 15.0,
                "min_rsi": 20.0,
                "max_rsi": 35.0,
                "require_above_ema": 200,
                "min_volume_ratio": 1.5,
                "min_ai_confidence": 70.0,
                "ai_direction_filter": "BUY"
            }
        }


class ScreenedInstrument(BaseModel):
    """Individual instrument that passed screening criteria"""
    symbol: str = Field(..., description="Instrument symbol")
    asset_class: str = Field(..., description="Asset class")
    exchange: str = Field(..., description="Exchange")
    current_price: float = Field(..., description="Current price")
    score: float = Field(..., ge=0, le=100, description="Composite screening score (0-100)")
    technical_score: float = Field(..., ge=0, le=100, description="Technical analysis score")
    fundamental_score: float = Field(..., ge=0, le=100, description="Fundamental score (0 for non-equity)")
    momentum_score: float = Field(..., ge=0, le=100, description="Momentum score")
    volume_score: float = Field(..., ge=0, le=100, description="Volume score")
    ai_signal: Optional[str] = Field(None, description="AI signal: BUY/SELL/HOLD")
    ai_confidence: Optional[float] = Field(None, ge=0, le=100, description="AI confidence (0-100)")
    reasons: List[str] = Field(..., description="Human-readable reasons why it passed")
    quick_stats: dict = Field(..., description="Quick stats: rsi, ema_position, volume_ratio, atr, etc.")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "RELIANCE",
                "asset_class": "equity",
                "exchange": "NSE",
                "current_price": 2450.50,
                "score": 85.5,
                "technical_score": 82.0,
                "fundamental_score": 88.0,
                "momentum_score": 78.0,
                "volume_score": 92.0,
                "ai_signal": "BUY",
                "ai_confidence": 85.0,
                "reasons": [
                    "RSI oversold at 28.5",
                    "Price above 200 EMA",
                    "Volume 2.3x average",
                    "Strong fundamentals: ROE 18.5%"
                ],
                "quick_stats": {
                    "rsi": 28.5,
                    "ema_position": "above_200",
                    "volume_ratio": 2.3,
                    "atr": 45.2,
                    "adx": 32.5
                }
            }
        }


class ScreeningResult(BaseModel):
    """Result of a screening run"""
    screening_id: str = Field(..., description="Unique screening run ID")
    criteria_name: str = Field(..., description="Name of the criteria used")
    run_at: str = Field(..., description="ISO timestamp when screening was run")
    duration_seconds: float = Field(..., description="Time taken to complete screening")
    instruments_scanned: int = Field(..., description="Total instruments scanned")
    instruments_passed: int = Field(..., description="Instruments that passed criteria")
    results: List[ScreenedInstrument] = Field(..., description="Top instruments that passed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "screening_id": "550e8400-e29b-41d4-a716-446655440000",
                "criteria_name": "Oversold Reversal Scanner",
                "run_at": "2025-01-15T10:30:00Z",
                "duration_seconds": 12.5,
                "instruments_scanned": 2000,
                "instruments_passed": 15,
                "results": []
            }
        }
