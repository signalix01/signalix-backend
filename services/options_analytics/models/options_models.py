"""
Options Analytics Database Models

SQLAlchemy ORM models for options chain data, Greeks calculation, and strategy builder.
Requirements: 4.1, 7.1, 19.1, 31.1
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
    Numeric,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base, Mapped, mapped_column

Base = declarative_base()


class OptionType(str, PyEnum):
    """Option type enumeration"""
    CALL = "CALL"
    PUT = "PUT"


class PositionType(str, PyEnum):
    """Position type (long/short)"""
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyType(str, PyEnum):
    """Options strategy types"""
    SINGLE = "SINGLE"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    BUTTERFLY = "BUTTERFLY"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    CUSTOM = "CUSTOM"


class OIPattern(str, PyEnum):
    """Open Interest change patterns"""
    BULLISH_BUILDUP = "BULLISH_BUILDUP"
    BEARISH_BUILDUP = "BEARISH_BUILDUP"
    BULLISH_UNWINDING = "BULLISH_UNWINDING"
    BEARISH_UNWINDING = "BEARISH_UNWINDING"
    NEUTRAL = "NEUTRAL"


class OptionsChain(Base):
    """
    Options chain data for a symbol on a specific date
    
    Requirements: 19.1, 19.2, 19.3, 19.4
    """
    __tablename__ = "options_chains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    spot_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    underlying_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    
    # Market data
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Metadata
    total_call_oi: Mapped[int] = mapped_column(Integer, default=0)
    total_put_oi: Mapped[int] = mapped_column(Integer, default=0)
    total_call_volume: Mapped[int] = mapped_column(Integer, default=0)
    total_put_volume: Mapped[int] = mapped_column(Integer, default=0)
    pcr_oi: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0)
    pcr_volume: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0)
    
    # Relationships
    strikes: Mapped[List["OptionStrike"]] = relationship(
        "OptionStrike",
        back_populates="chain",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        UniqueConstraint("symbol", "expiry_date", "timestamp", name="uq_options_chain_symbol_expiry_time"),
        Index("idx_options_chain_symbol_expiry", "symbol", "expiry_date"),
        Index("idx_options_chain_timestamp", "timestamp"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "spot_price": float(self.spot_price),
            "underlying_price": float(self.underlying_price),
            "timestamp": self.timestamp.isoformat(),
            "total_call_oi": self.total_call_oi,
            "total_put_oi": self.total_put_oi,
            "total_call_volume": self.total_call_volume,
            "total_put_volume": self.total_put_volume,
            "pcr_oi": float(self.pcr_oi),
            "pcr_volume": float(self.pcr_volume),
            "strikes": [s.to_dict() for s in self.strikes] if self.strikes else [],
        }


class OptionStrike(Base):
    """
    Individual option strike data
    
    Requirements: 19.3, 19.4, 19.5, 19.10
    """
    __tablename__ = "option_strikes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("options_chains.id", ondelete="CASCADE"), nullable=False
    )
    
    strike_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    
    # Call option data
    call_ltp: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    call_bid: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    call_ask: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    call_oi: Mapped[int] = mapped_column(Integer, default=0)
    call_volume: Mapped[int] = mapped_column(Integer, default=0)
    call_iv: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    
    # Put option data
    put_ltp: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    put_bid: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    put_ask: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    put_oi: Mapped[int] = mapped_column(Integer, default=0)
    put_volume: Mapped[int] = mapped_column(Integer, default=0)
    put_iv: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    
    # Greeks (stored for caching)
    call_delta: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    call_gamma: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    call_theta: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    call_vega: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    call_rho: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    
    put_delta: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    put_gamma: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    put_theta: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    put_vega: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    put_rho: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    
    # Relationships
    chain: Mapped["OptionsChain"] = relationship("OptionsChain", back_populates="strikes")
    
    __table_args__ = (
        UniqueConstraint("chain_id", "strike_price", name="uq_strike_chain_strike"),
        Index("idx_option_strike_chain", "chain_id"),
        Index("idx_option_strike_price", "strike_price"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "strike_price": float(self.strike_price),
            "call": {
                "ltp": float(self.call_ltp) if self.call_ltp else None,
                "bid": float(self.call_bid) if self.call_bid else None,
                "ask": float(self.call_ask) if self.call_ask else None,
                "oi": self.call_oi,
                "volume": self.call_volume,
                "iv": float(self.call_iv) if self.call_iv else None,
                "greeks": {
                    "delta": float(self.call_delta) if self.call_delta else None,
                    "gamma": float(self.call_gamma) if self.call_gamma else None,
                    "theta": float(self.call_theta) if self.call_theta else None,
                    "vega": float(self.call_vega) if self.call_vega else None,
                    "rho": float(self.call_rho) if self.call_rho else None,
                } if self.call_delta else None,
            },
            "put": {
                "ltp": float(self.put_ltp) if self.put_ltp else None,
                "bid": float(self.put_bid) if self.put_bid else None,
                "ask": float(self.put_ask) if self.put_ask else None,
                "oi": self.put_oi,
                "volume": self.put_volume,
                "iv": float(self.put_iv) if self.put_iv else None,
                "greeks": {
                    "delta": float(self.put_delta) if self.put_delta else None,
                    "gamma": float(self.put_gamma) if self.put_gamma else None,
                    "theta": float(self.put_theta) if self.put_theta else None,
                    "vega": float(self.put_vega) if self.put_vega else None,
                    "rho": float(self.put_rho) if self.put_rho else None,
                } if self.put_delta else None,
            },
        }


class Greeks(Base):
    """
    Greeks calculation results stored for caching
    
    Requirements: 38.1, 38.2, 38.3, 38.4, 38.5, 38.7
    """
    __tablename__ = "greeks_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    strike_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    option_type: Mapped[OptionType] = mapped_column(Enum(OptionType), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Input parameters
    spot_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    risk_free_rate: Mapped[float] = mapped_column(Numeric(10, 6), default=0.06)
    implied_volatility: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    market_price: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    
    # Greeks values
    delta: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    gamma: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    theta: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    vega: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    rho: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    
    # Metadata
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    time_to_expiry: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)  # in years
    
    __table_args__ = (
        UniqueConstraint(
            "symbol", "strike_price", "option_type", "expiry_date", "spot_price",
            name="uq_greeks_cache"
        ),
        Index("idx_greeks_cache_symbol_expiry", "symbol", "expiry_date"),
        Index("idx_greeks_cache_calculated", "calculated_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "strike_price": float(self.strike_price),
            "option_type": self.option_type.value,
            "expiry_date": self.expiry_date.isoformat(),
            "spot_price": float(self.spot_price),
            "risk_free_rate": float(self.risk_free_rate),
            "implied_volatility": float(self.implied_volatility) if self.implied_volatility else None,
            "market_price": float(self.market_price) if self.market_price else None,
            "delta": float(self.delta),
            "gamma": float(self.gamma),
            "theta": float(self.theta),
            "vega": float(self.vega),
            "rho": float(self.rho),
            "calculated_at": self.calculated_at.isoformat(),
            "time_to_expiry": float(self.time_to_expiry),
        }


class OptionsStrategy(Base):
    """
    Multi-leg options strategy configuration
    
    Requirements: 7.6, 26.1, 45.1, 45.2
    """
    __tablename__ = "options_strategies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    strategy_type: Mapped[StrategyType] = mapped_column(Enum(StrategyType), default=StrategyType.CUSTOM)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Strategy metrics
    max_profit: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    max_loss: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    breakeven_points: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)
    margin_required: Mapped[Optional[float]] = mapped_column(Numeric(15, 4), nullable=True)
    
    # Payoff data (cached)
    payoff_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    legs: Mapped[List["StrategyLeg"]] = relationship(
        "StrategyLeg",
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index("idx_options_strategy_user", "user_id"),
        Index("idx_options_strategy_symbol", "symbol"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "description": self.description,
            "strategy_type": self.strategy_type.value,
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "max_profit": float(self.max_profit) if self.max_profit else None,
            "max_loss": float(self.max_loss) if self.max_loss else None,
            "breakeven_points": self.breakeven_points,
            "margin_required": float(self.margin_required) if self.margin_required else None,
            "payoff_data": self.payoff_data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "legs": [leg.to_dict() for leg in self.legs] if self.legs else [],
        }


class StrategyLeg(Base):
    """
    Individual leg of an options strategy
    
    Requirements: 26.2, 26.3, 26.4
    """
    __tablename__ = "strategy_legs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("options_strategies.id", ondelete="CASCADE"), nullable=False
    )
    
    # Leg details
    leg_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3, etc.
    option_type: Mapped[OptionType] = mapped_column(Enum(OptionType), nullable=False)
    position_type: Mapped[PositionType] = mapped_column(Enum(PositionType), nullable=False)
    strike_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    
    # Entry price (for payoff calculation)
    entry_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    
    # Relationships
    strategy: Mapped["OptionsStrategy"] = relationship("OptionsStrategy", back_populates="legs")
    
    __table_args__ = (
        UniqueConstraint("strategy_id", "leg_number", name="uq_strategy_leg_number"),
        Index("idx_strategy_leg_strategy", "strategy_id"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "leg_number": self.leg_number,
            "option_type": self.option_type.value,
            "position_type": self.position_type.value,
            "strike_price": float(self.strike_price),
            "quantity": self.quantity,
            "entry_price": float(self.entry_price),
        }


class MaxPainResult(Base):
    """
    Max pain calculation results
    
    Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7
    """
    __tablename__ = "max_pain_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    max_pain_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    current_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    deviation_percent: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    
    # Detailed loss at each strike
    loss_by_strike: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("symbol", "expiry_date", name="uq_max_pain_symbol_expiry"),
        Index("idx_max_pain_symbol", "symbol"),
        Index("idx_max_pain_calculated", "calculated_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "max_pain_price": float(self.max_pain_price),
            "current_price": float(self.current_price),
            "deviation_percent": float(self.deviation_percent),
            "loss_by_strike": self.loss_by_strike,
            "calculated_at": self.calculated_at.isoformat(),
        }


class GEXResult(Base):
    """
    Gamma Exposure (GEX) calculation results
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7
    """
    __tablename__ = "gex_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    spot_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    
    # GEX distribution by strike
    gex_distribution: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # Key levels
    zero_gamma_level: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    significant_levels: Mapped[List[float]] = mapped_column(JSON, nullable=False)
    
    # Totals
    total_call_gex: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    total_put_gex: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    net_gex: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("symbol", "expiry_date", name="uq_gex_symbol_expiry"),
        Index("idx_gex_symbol", "symbol"),
        Index("idx_gex_calculated", "calculated_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "spot_price": float(self.spot_price),
            "gex_distribution": self.gex_distribution,
            "zero_gamma_level": float(self.zero_gamma_level),
            "significant_levels": self.significant_levels,
            "total_call_gex": float(self.total_call_gex),
            "total_put_gex": float(self.total_put_gex),
            "net_gex": float(self.net_gex),
            "calculated_at": self.calculated_at.isoformat(),
        }


class OIChange(Base):
    """
    Open Interest change tracking
    
    Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
    """
    __tablename__ = "oi_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    strike_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    option_type: Mapped[OptionType] = mapped_column(Enum(OptionType), nullable=False)
    
    # OI data
    current_oi: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_oi: Mapped[int] = mapped_column(Integer, nullable=False)
    absolute_change: Mapped[int] = mapped_column(Integer, nullable=False)
    percent_change: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    
    # Pattern classification
    pattern: Mapped[OIPattern] = mapped_column(Enum(OIPattern), nullable=False)
    
    # Price context
    price_change: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0)
    
    # Time interval for this change (1m, 5m, 1h, 1d)
    interval: Mapped[str] = mapped_column(String(10), default="5m")
    
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_oi_change_symbol_expiry", "symbol", "expiry_date"),
        Index("idx_oi_change_strike", "strike_price"),
        Index("idx_oi_change_calculated", "calculated_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "strike_price": float(self.strike_price),
            "option_type": self.option_type.value,
            "current_oi": self.current_oi,
            "previous_oi": self.previous_oi,
            "absolute_change": self.absolute_change,
            "percent_change": float(self.percent_change),
            "pattern": self.pattern.value,
            "price_change": float(self.price_change),
            "interval": self.interval,
            "calculated_at": self.calculated_at.isoformat(),
        }


class HistoricalOptionsData(Base):
    """
    Historical options chain data storage
    
    Requirements: 59.1, 59.2, 59.3, 59.4
    """
    __tablename__ = "historical_options_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Summary data
    spot_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    total_call_oi: Mapped[int] = mapped_column(Integer, default=0)
    total_put_oi: Mapped[int] = mapped_column(Integer, default=0)
    pcr_oi: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0)
    
    # Analytics data (stored as JSON)
    max_pain_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    gex_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    iv_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Full chain data (compressed/aggregated)
    chain_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("symbol", "expiry_date", "data_date", name="uq_historical_options_data"),
        Index("idx_historical_options_symbol", "symbol"),
        Index("idx_historical_options_date", "data_date"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "expiry_date": self.expiry_date.isoformat(),
            "data_date": self.data_date.isoformat(),
            "spot_price": float(self.spot_price),
            "total_call_oi": self.total_call_oi,
            "total_put_oi": self.total_put_oi,
            "pcr_oi": float(self.pcr_oi),
            "max_pain_data": self.max_pain_data,
            "gex_data": self.gex_data,
            "iv_data": self.iv_data,
            "created_at": self.created_at.isoformat(),
        }
