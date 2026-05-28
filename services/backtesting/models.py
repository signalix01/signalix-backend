"""
Pydantic models for backtesting configuration and results.

Requirements: 4.1, 4.5, 4.6, 4.7, 4.8
"""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from enum import Enum
from services.algo_builder.models import StrategySpec


class BacktestMode(str, Enum):
    """Backtesting mode"""
    VECTORISED = "vectorised"  # Fast mode: 10+ years in seconds. Uses vectorbt.
    EVENT_DRIVEN = "event"  # Realistic mode: bar-by-bar simulation with slippage


class SlippageModel(str, Enum):
    """Slippage model types"""
    FIXED_PIPS = "fixed_pips"
    PCT_SPREAD = "pct_spread"
    MARKET_IMPACT = "market_impact"


class BacktestConfig(BaseModel):
    """Configuration for a backtest run"""
    strategy_spec: StrategySpec
    instrument: str
    start_date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    end_date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    initial_capital: float = Field(..., description="Initial capital in Rs/USD")
    mode: BacktestMode = BacktestMode.VECTORISED
    
    # Realism settings (event-driven mode)
    slippage_model: SlippageModel = SlippageModel.PCT_SPREAD
    slippage_value: float = Field(default=0.05, description="0.05% spread as slippage")
    brokerage_pct: float = Field(default=0.03, description="Angel One intraday: 0.03%")
    brokerage_fixed: float = Field(default=20.0, description="Rs 20 per order (Zerodha flat fee model)")
    stt_rate: float = Field(default=0.025, description="Securities Transaction Tax")
    gst_rate: float = Field(default=18.0, description="GST on brokerage")
    
    # Validation settings
    run_walk_forward: bool = True
    wf_train_pct: float = 0.70
    wf_validate_pct: float = 0.15
    wf_test_pct: float = 0.15
    run_monte_carlo: bool = False
    monte_carlo_simulations: int = 10000
    run_regime_analysis: bool = True  # Paul Tudor Jones: regime-stratified results


class BacktestResult(BaseModel):
    """Complete backtest result"""
    backtest_id: str
    strategy_id: str
    instrument: str
    period: str
    mode: BacktestMode
    
    # Core performance metrics
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: float = Field(..., description="Target: > 1.5 for acceptable strategy")
    sortino_ratio: float = Field(..., description="Target: > 2.0")
    calmar_ratio: float = Field(..., description="CAGR / max drawdown")
    max_drawdown_pct: float = Field(..., description="Druckenmiller rule: must be < 15%")
    avg_drawdown_pct: float
    max_drawdown_duration_days: int
    
    # Trade statistics
    total_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float = Field(..., description="Gross profit / gross loss, target > 1.5")
    expectancy_per_trade: float = Field(..., description="Rs per trade")
    avg_hold_days: float
    max_consecutive_losses: int
    
    # Risk metrics (Edward Thorp Kelly-based)
    kelly_fraction: float = Field(..., description="Optimal position size")
    half_kelly: float = Field(..., description="Recommended conservative size")
    
    # Walk-forward results
    wf_train_return: Optional[float] = None
    wf_validate_return: Optional[float] = None
    wf_test_return: Optional[float] = None
    wf_consistency_score: float = Field(default=0.0, description="0-1: how consistent across periods")
    
    # Regime analysis
    trending_bull_return: Optional[float] = None
    trending_bear_return: Optional[float] = None
    ranging_return: Optional[float] = None
    volatile_return: Optional[float] = None
    
    # Monte Carlo (if enabled)
    mc_median_return: Optional[float] = None
    mc_5th_percentile_return: Optional[float] = None
    mc_95th_percentile_return: Optional[float] = None
    mc_ruin_probability: Optional[float] = None  # P(capital < 50% of initial)
    
    # Trade list
    trades: List[dict] = Field(..., description="Each trade: entry_date, exit_date, direction, pnl_pct, exit_reason")
    equity_curve: List[float] = Field(..., description="Daily portfolio values")
    drawdown_curve: List[float] = Field(..., description="Daily drawdown %")
    
    class Config:
        use_enum_values = True
