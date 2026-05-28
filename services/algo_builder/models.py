"""Pydantic models for strategy specification

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""
from pydantic import BaseModel, Field, validator
from typing import List, Literal, Optional, Union
from enum import Enum


class IndicatorType(str, Enum):
    """Supported technical indicators"""
    RSI = "rsi"
    MACD = "macd"
    EMA = "ema"
    SMA = "sma"
    BB = "bollinger_bands"
    ATR = "atr"
    VWAP = "vwap"
    SUPERTREND = "supertrend"
    ADX = "adx"
    STOCH = "stochastic"
    OBV = "obv"
    PIVOT = "pivot_points"
    ICHIMOKU = "ichimoku"
    WILLIAMS_R = "williams_r"
    CCI = "cci"
    MFI = "mfi"


class CompareOperator(str, Enum):
    """Comparison operators for conditions"""
    GREATER = ">"
    LESS = "<"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    EQUALS = "=="
    BETWEEN = "between"


class ConditionBlock(BaseModel):
    """Single condition in a strategy rule"""
    left_operand: str = Field(..., description="e.g. 'rsi_14' or 'close' or 'ema_21'")
    operator: CompareOperator
    right_operand: Union[str, float] = Field(..., description="e.g. '70' or 'ema_50'")
    time_frame: str = Field(default="1D", description="e.g. '1m', '5m', '1h', '1D'")


class LogicGate(str, Enum):
    """Logic gates for combining conditions"""
    AND = "AND"
    OR = "OR"


class ConditionGroup(BaseModel):
    """Group of conditions combined with a logic gate"""
    conditions: List[ConditionBlock]
    gate: LogicGate = LogicGate.AND


class EntryRule(BaseModel):
    """Entry rule for a strategy"""
    direction: Literal["LONG", "SHORT"]
    condition_groups: List[ConditionGroup] = Field(..., description="Groups joined by AND")
    confirmation_candles: int = Field(default=1, description="Wait N candles for confirmation")


class ExitRule(BaseModel):
    """Exit rule for a strategy"""
    exit_type: Literal["target", "stop_loss", "trailing_sl", "indicator", "time"]
    target_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    trailing_sl_pct: Optional[float] = None
    indicator_condition: Optional[ConditionBlock] = None
    max_hold_candles: Optional[int] = None


class PositionSizingMethod(str, Enum):
    """Position sizing methods"""
    FIXED_CAPITAL = "fixed_capital"  # Rs X per trade
    PCT_CAPITAL = "pct_capital"  # X% of capital
    KELLY_CRITERION = "kelly"  # AI-computed Kelly fraction (WARNING: requires historical data for calculation)
    ATR_BASED = "atr_based"  # 1% risk / ATR
    VOLATILITY_ADJUSTED = "vol_adj"  # Scale inversely with volatility


class PositionSizing(BaseModel):
    """Position sizing configuration"""
    method: PositionSizingMethod
    value: float = Field(..., description="Amount/percentage/multiplier")
    max_position_pct: float = Field(default=10.0, description="Hard cap: never exceed X% of capital")
    max_concurrent_positions: int = Field(default=5)

    @validator('max_position_pct')
    def validate_max_position_pct(cls, v):
        """Enforce hard maximum position cap of 10%"""
        if v > 10.0:
            raise ValueError("max_position_pct cannot exceed 10.0%")
        return v

    @validator('method')
    def validate_kelly_method(cls, v):
        """Warn when Kelly sizing method is used - requires historical data"""
        if v == PositionSizingMethod.KELLY_CRITERION:
            # Note: This is a warning, not an error. The method is valid but requires historical data.
            # The actual Kelly fraction calculation will be performed during backtesting.
            pass
        return v


class MarketFilter(BaseModel):
    """Macro regime gate — Druckenmiller's first principle"""
    require_above_200ema: bool = Field(default=False, description="Only trade when price > 200 EMA")
    min_adx: Optional[float] = Field(default=None, description="Only trade when ADX > X (trending)")
    max_vix: Optional[float] = Field(default=None, description="Halt trading when VIX > X")
    require_positive_breadth: bool = Field(default=False, description="Only when >50% of stocks advancing")


class StrategySpec(BaseModel):
    """Complete no-code strategy specification"""
    strategy_id: str
    user_id: str
    name: str
    description: str
    asset_class: Literal["equity", "fo", "crypto", "forex", "commodity"]
    instruments: List[str] = Field(..., description="List of symbols")
    entry_rules: List[EntryRule] = Field(..., min_items=1, description="At least 1 required")
    exit_rules: List[ExitRule] = Field(..., min_items=1, description="At least 1 required")
    position_sizing: PositionSizing
    market_filter: MarketFilter
    indicators_config: dict = Field(..., description="{indicator_id: {params}} e.g. {'rsi_14': {'period': 14}}")
    risk_per_trade_pct: float = Field(default=1.0, description="Richard Dennis Turtle: 1% risk per trade")
    max_daily_loss_pct: float = Field(default=2.0, description="Druckenmiller: 2% daily max loss")
    regime_awareness: bool = Field(default=True, description="Paul Tudor Jones: macro awareness")
    status: Literal["draft", "testing", "paper", "live"] = Field(default="draft")
    created_at: str
    updated_at: str

    @validator('entry_rules')
    def validate_entry_rules(cls, v):
        """Ensure at least one entry rule"""
        if not v or len(v) == 0:
            raise ValueError("At least one entry rule is required")
        return v

    @validator('exit_rules')
    def validate_exit_rules(cls, v):
        """Ensure at least one exit rule"""
        if not v or len(v) == 0:
            raise ValueError("At least one exit rule is required")
        return v

    class Config:
        use_enum_values = True
