"""
Agent Output Schemas

Pydantic models for all 13 AI agent outputs in the LangGraph analysis pipeline.
Each model defines the structured output format that agents must return.
Strictly SEBI-compliant: uses objective terminology, avoids prescriptive advice.

These schemas are used by:
- agents/*.py (individual agent modules)
- orchestration/langgraph_pipeline.py (pipeline state management)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Stage 0 — Pre-Screening
# =============================================================================

class ScreeningDecision(BaseModel):
    """Pre-screener gate decision: should instrument enter the full pipeline?"""

    pass_screening: bool = Field(
        ..., description="Whether instrument passed pre-screening"
    )
    confidence_floor_met: bool = Field(
        False, description="Whether minimum confidence threshold is met"
    )
    instrument_type_confirmed: str = Field(
        "unknown",
        description="Confirmed instrument type (equity, futures, options, crypto, forex, commodity)",
    )
    market_session_valid: bool = Field(
        False, description="Whether market session is currently valid"
    )
    data_quality_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Data quality score 0-1"
    )
    skip_reason: Optional[str] = Field(
        None, description="Reason for skipping full analysis (if rejected)"
    )


class MarketRegimeReport(BaseModel):
    """Market regime classification for adaptive exposure modeling."""

    regime: str = Field(
        ...,
        description="Market regime: trending_bull, trending_bear, volatile, crisis, ranging",
    )
    vix_level: float = Field(0.0, description="Current VIX level")
    vix_regime: str = Field(
        "normal", description="VIX regime: low, normal, elevated, extreme"
    )
    global_risk_sentiment: str = Field(
        "neutral", description="Global risk sentiment: risk_on, neutral, risk_off"
    )
    forex_dollar_index: float = Field(0.0, description="DXY dollar index level")
    regime_confidence: float = Field(
        0.5, ge=0.0, le=1.0, description="Confidence in regime classification"
    )
    position_size_multiplier: float = Field(
        1.0,
        ge=0.0,
        le=2.0,
        description="Multiplier for theoretical exposure modeling (0=sit out, 2=max conviction)",
    )
    key_observations: List[str] = Field(
        default_factory=list, description="Key macro observations"
    )


# =============================================================================
# Stage 1 — Parallel Analysts
# =============================================================================

class FundamentalsReport(BaseModel):
    """Fundamentals analyst output — company/instrument financial metrics."""

    fundamental_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall fundamental score 0-10"
    )
    fair_value_estimate: Optional[float] = Field(
        None, description="Estimated fair value based on analytical models"
    )
    current_valuation: str = Field(
        "fairly valued",
        description="Valuation status: undervalued, fairly valued, overvalued",
    )
    key_insight: str = Field("", description="Key fundamental insight")
    growth_drivers: List[str] = Field(
        default_factory=list, description="Growth drivers and observed positive factors"
    )
    risk_factors: List[str] = Field(
        default_factory=list, description="Observed risk factors"
    )
    upcoming_catalysts: List[str] = Field(
        default_factory=list, description="Upcoming scheduled events/catalysts"
    )
    sector: str = Field("", description="Sector classification")
    analytical_bias: str = Field(
        "neutral", description="Analytical bias/stance: strongly_bullish, bullish, neutral, bearish, strongly_bearish"
    )


class TechnicalReport(BaseModel):
    """Technical analyst output — chart patterns, indicators, and key observed levels."""

    technical_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall technical score 0-10"
    )
    trend: str = Field(
        "sideways", description="Trend: uptrend, downtrend, sideways"
    )
    key_insight: str = Field("", description="Key technical insight")
    entry_price: Optional[float] = Field(None, description="Observed technical breakout/support level")
    stop_loss: Optional[float] = Field(None, description="Key lower validation/invalidation support bound")
    target_1: Optional[float] = Field(None, description="Technical projection resistance marker 1")
    target_2: Optional[float] = Field(None, description="Technical projection resistance marker 2")
    target_3: Optional[float] = Field(None, description="Technical projection resistance marker 3")
    support_levels: List[float] = Field(
        default_factory=list, description="Key support levels"
    )
    resistance_levels: List[float] = Field(
        default_factory=list, description="Key resistance levels"
    )
    indicators: Dict[str, Any] = Field(
        default_factory=dict,
        description="Technical indicators (rsi, macd, moving_averages, etc.)",
    )
    chart_pattern: Optional[str] = Field(None, description="Identified chart pattern")
    risk_reward_ratio: float = Field(0.0, description="Computed risk/reward metrics")
    analytical_bias: str = Field("neutral", description="Technical analytical bias")


class MacroReport(BaseModel):
    """Macro analyst output — macroeconomic environment tracking."""

    macro_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall macro score 0-10"
    )
    market_regime: str = Field(
        "neutral",
        description="Market regime: risk_on, neutral, risk_off, crisis",
    )
    key_insight: str = Field("", description="Key macro insight")
    supportive_factors: List[str] = Field(
        default_factory=list, description="Supportive macro factors"
    )
    headwinds: List[str] = Field(
        default_factory=list, description="Macro headwinds"
    )
    currency_impact: str = Field(
        "neutral", description="Currency impact: positive, neutral, negative"
    )
    liquidity_conditions: str = Field(
        "adequate", description="Liquidity: ample, adequate, tight"
    )
    sector_impact: str = Field("", description="Sector-specific macro impact")
    upcoming_events: List[str] = Field(
        default_factory=list, description="Upcoming macro events"
    )
    analytical_bias: str = Field("neutral", description="Macro analytical bias")


class SentimentReport(BaseModel):
    """Sentiment analyst output — market sentiment and social analysis."""

    sentiment_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall sentiment score 0-10"
    )
    sentiment_trend: str = Field(
        "stable",
        description="Sentiment trend: improving, stable, deteriorating",
    )
    key_insight: str = Field("", description="Key sentiment insight")
    social_media_buzz: str = Field(
        "medium", description="Social media buzz: low, medium, high"
    )
    news_sentiment: str = Field(
        "neutral", description="News sentiment: positive, neutral, negative"
    )
    analyst_consensus: str = Field(
        "neutral", description="External analyst consensus track: bullish, neutral, bearish"
    )
    retail_interest: str = Field(
        "medium", description="Retail interest: low, medium, high"
    )
    contrarian_signal: bool = Field(
        False, description="Whether extreme sentiment represents an objective divergence"
    )
    sentiment_drivers: List[str] = Field(
        default_factory=list, description="Key sentiment drivers"
    )
    analytical_bias: str = Field("neutral", description="Sentiment analytical bias")


class NewsFlashReport(BaseModel):
    """News scanner output — real-time event detection metrics."""

    breaking_news: bool = Field(
        False, description="Whether breaking news is detected"
    )
    news_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of news items: [{headline, source, sentiment, impact}]",
    )
    aggregate_news_sentiment: float = Field(
        0.0, ge=-1.0, le=1.0, description="Aggregate news sentiment -1 to +1"
    )
    event_risk_flag: bool = Field(
        False, description="Whether a material event risk is flagged"
    )
    social_sentiment_score: float = Field(
        0.0, ge=-1.0, le=1.0, description="Social media sentiment -1 to +1"
    )
    retail_positioning: str = Field(
        "neutral", description="Retail positioning: bullish, neutral, bearish"
    )
    analytical_bias: str = Field(
        "proceed",
        description="News evaluation stance: proceed, caution, halt",
    )
    key_insight: str = Field("", description="Key news insight")


# =============================================================================
# Stage 1 — Conditional Specialists
# =============================================================================

class ForexMacroReport(BaseModel):
    """Forex/commodity macro analyst output — international market metrics."""

    primary_currency_pair: str = Field("N/A", description="Primary currency pair")
    dxy_trend: str = Field(
        "neutral", description="DXY trend: bullish, neutral, bearish"
    )
    central_bank_stance: Dict[str, str] = Field(
        default_factory=dict,
        description="Central bank stances: {fed, ecb, rbi, boj}",
    )
    carry_trade_conditions: str = Field(
        "neutral",
        description="Carry trade conditions: favorable, neutral, unfavorable",
    )
    geopolitical_risk_score: float = Field(
        0.5, ge=0.0, le=1.0, description="Geopolitical risk 0-1"
    )
    commodity_correlation: Optional[str] = Field(
        None, description="Commodity correlation assessment"
    )
    macro_bias: str = Field(
        "neutral", description="Macro bias: bullish, neutral, bearish"
    )
    confidence: float = Field(
        0.5, ge=0.0, le=1.0, description="Analysis confidence"
    )
    key_insight: str = Field("", description="Key forex/macro insight")


class DeepFundamentalsReport(BaseModel):
    """Deep fundamentals analyst output — comprehensive document evaluation."""

    earnings_quality_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Earnings quality score 0-10"
    )
    management_credibility: float = Field(
        5.0, ge=0.0, le=10.0, description="Management credibility 0-10"
    )
    balance_sheet_strength: float = Field(
        5.0, ge=0.0, le=10.0, description="Balance sheet strength 0-10"
    )
    earnings_surprise_history: str = Field(
        "na",
        description="Earnings surprise history: consistent_beat, mixed, consistent_miss, na",
    )
    regulatory_risk: float = Field(
        0.3, ge=0.0, le=1.0, description="Regulatory risk 0-1"
    )
    insider_activity_signal: str = Field(
        "na", description="Insider activity track: buying, neutral, selling, na"
    )
    dcf_implied_upside_pct: Optional[float] = Field(
        None, description="DCF-implied theoretical upside percentage"
    )
    analyst_consensus: Optional[str] = Field(
        None, description="External analyst consensus track: strong_buy, buy, hold, sell, strong_sell"
    )
    key_insight: str = Field("", description="Key deep fundamentals insight")


# =============================================================================
# Stage 2 — Bull/Bear Debate
# =============================================================================

class ResearchThesis(BaseModel):
    """Bull/bear researcher output — objective scenario analysis with conviction."""

    side: str = Field(
        ..., description="Thesis side scenario: bull or bear"
    )
    overall_conviction: float = Field(
        0.5, ge=0.0, le=1.0, description="Overall scenario conviction 0-1"
    )
    key_arguments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Key arguments: [{argument, evidence, conviction}]",
    )
    rebuttal: Optional[str] = Field(
        None, description="Rebuttal to opposing scenario"
    )
    debate_round: int = Field(1, ge=1, le=3, description="Current evaluation round")
    strongest_point: Optional[str] = Field(
        None, description="Single strongest observed argument"
    )
    weakest_point: Optional[str] = Field(
        None, description="Acknowledged weakest observed point in scenario"
    )


# =============================================================================
# Stage 3 — Risk & Validation
# =============================================================================

class QuantCheckReport(BaseModel):
    """Quantitative cross-check output — independent mathematical validation."""

    kelly_fraction_validated: bool = Field(
        True, description="Whether Kelly fraction passed math validation"
    )
    kelly_fraction_deepseek: float = Field(
        0.05, description="DeepSeek-computed Kelly fraction"
    )
    kelly_discrepancy_pct: float = Field(
        0.0, description="Discrepancy vs Risk evaluation Kelly (%)"
    )
    risk_reward_ratio: float = Field(0.0, description="Computed risk/reward ratio")
    expected_value_per_trade: float = Field(
        0.0, description="Expected value metric per trade scenario"
    )
    monte_carlo_win_rate: float = Field(
        0.5, ge=0.0, le=1.0, description="Monte Carlo simulated probability metric"
    )
    sharpe_estimate: float = Field(0.0, description="Estimated Sharpe ratio metric")
    theoretical_exposure_weight: float = Field(
        5.0, description="Theoretical allocation guideline as % of capital"
    )
    override_flag: bool = Field(
        False,
        description="True if discrepancy >15% — signals mathematical mismatch",
    )
    override_reason: Optional[str] = Field(
        None, description="Reason for override validation flag"
    )


class RiskAssessment(BaseModel):
    """Risk manager output — theoretical exposure modeling and statistical bounds."""

    risk_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall risk score 0-10 (lower=less volatile)"
    )
    key_insight: str = Field("", description="Key risk evaluation insight")
    theoretical_exposure_weight: str = Field(
        "5% of capital", description="Theoretical exposure allocation guideline"
    )
    risk_reward_ratio: float = Field(0.0, description="Computed risk/reward ratio")
    max_loss_potential: str = Field("", description="Maximum statistical loss potential")
    kelly_fraction: float = Field(
        0.05, ge=0.0, le=1.0, description="Kelly criterion fraction metric"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Observed statistical risk warnings"
    )
    circuit_breakers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Observed dynamic boundaries (stop_loss, trailing_stop, time_stop)",
    )
    portfolio_impact: Dict[str, Any] = Field(
        default_factory=dict,
        description="Theoretical portfolio impact (sector_concentration, correlation_risk)",
    )
    risk_stance: str = Field(
        "approve", description="Risk evaluation stance: approve, reduce, reject"
    )


# =============================================================================
# Stage 4 — Final Synthesis
# =============================================================================

class MarketSynthesisOutcome(BaseModel):
    """Final synthesis output — aggregated objective analytics report."""

    direction: str = Field(
        "neutral", description="Analyzed bias direction: bullish, bearish, neutral"
    )
    confidence_score: float = Field(
        5.0, ge=0.0, le=10.0, description="Overall multi-factor agreement score 0-10"
    )
    entry_price: Optional[float] = Field(None, description="Observed reference breakout/support entry bound")
    stop_loss: Optional[float] = Field(None, description="Observed lower reference support bound")
    target_1: Optional[float] = Field(None, description="Observed resistance target bound 1")
    target_2: Optional[float] = Field(None, description="Observed resistance target bound 2")
    target_3: Optional[float] = Field(None, description="Observed resistance target bound 3")
    holding_period: str = Field("", description="Observed reference scenario duration")
    rationale: str = Field("", description="Comprehensive multi-factor synthesis rationale")
    key_levels: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Key observed levels: {support: [...], resistance: [...]}",
    )
    risk_reward_ratio: float = Field(0.0, description="Computed risk/reward ratio")
    win_probability: float = Field(
        0.5, ge=0.0, le=1.0, description="Estimated theoretical success probability metric"
    )
    position_size_pct: float = Field(
        5.0, description="Theoretical position exposure guideline as % of capital"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Observed analytical divergence warnings"
    )
    analytical_bias: str = Field(
        "neutral",
        description="Synthesized overall analytical bias: strongly_bullish, bullish, neutral, bearish, strongly_bearish",
    )
    recommendation: Optional[str] = Field(
        None, description="Legacy alias property for backward compatibility with UI consumption"
    )
    avg_win_pct: Optional[float] = Field(None, description="Average tracked win percentage")
    avg_loss_pct: Optional[float] = Field(None, description="Average tracked loss percentage")
    sector: Optional[str] = Field(None, description="Instrument sector classification")
    macro_context: Optional[str] = Field(None, description="Aggregated macro baseline context")
    sentiment_summary: Optional[str] = Field(None, description="Aggregated sentiment synthesis")
    llm_response: Optional[str] = Field(None, description="Raw generation output string")
    agents_executed: List[str] = Field(default_factory=list, description="List of executed pipeline agents")
    total_cost_usd: float = Field(0.0, description="Total pipeline processing cost in USD")
    processing_time_seconds: float = Field(0.0, description="Total pipeline execution latency in seconds")
    sebi_disclaimer: str = Field(
        "DISCLAIMER: SignalixAI AI is an objective multi-factor market analytics software platform. Not SEBI registered. No buy/sell/hold advisory is provided. Users must consult a SEBI registered financial advisor.",
        description="Mandatory institutional regulatory disclosure",
    )


# Backward compatibility alias mapping to prevent orchestration import errors
TradingDecision = MarketSynthesisOutcome

