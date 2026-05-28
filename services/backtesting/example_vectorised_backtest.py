"""
Example: Running a vectorised backtest with the VectorisedEngine.

This example demonstrates how to:
1. Generate sample data (or use the data pipeline)
2. Create a strategy specification
3. Configure a backtest
4. Run the backtest
5. Analyze the results
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.backtesting.vectorised_engine import VectorisedEngine, VECTORBT_AVAILABLE
from services.backtesting.models import BacktestConfig, BacktestMode
from services.algo_builder.models import (
    StrategySpec, EntryRule, ExitRule, PositionSizing, MarketFilter,
    ConditionBlock, ConditionGroup, CompareOperator, PositionSizingMethod
)


def generate_banknifty_sample_data():
    """
    Generate realistic BANKNIFTY sample data.
    
    In production, this would be replaced with:
    ```python
    from services.backtesting.data_pipeline import BacktestDataPipeline
    pipeline = BacktestDataPipeline()
    data = await pipeline.get_backtest_data(
        instrument="BANKNIFTY",
        start="2019-01-01",
        end="2023-12-31",
        timeframe="1D",
        asset_class="NSE_EQUITY"
    )
    ```
    """
    print("Generating BANKNIFTY sample data...")
    
    # 5 years of daily data
    dates = pd.date_range(start='2019-01-01', end='2023-12-31', freq='D')
    n = len(dates)
    
    # Simulate BANKNIFTY price movement (started around 28000, now around 45000)
    np.random.seed(42)
    trend = np.linspace(28000, 45000, n)
    volatility = 500  # BANKNIFTY is volatile
    noise = np.random.normal(0, volatility, n)
    close = trend + noise
    
    # Generate OHLC
    high = close + np.random.uniform(0, volatility * 0.5, n)
    low = close - np.random.uniform(0, volatility * 0.5, n)
    open_price = close + np.random.uniform(-volatility * 0.3, volatility * 0.3, n)
    volume = np.random.uniform(50000, 200000, n)  # Typical BANKNIFTY volume
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    # Compute indicators (in production, data_pipeline.compute_indicators() does this)
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # EMAs
    for period in [9, 21, 50, 200]:
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr_14'] = true_range.rolling(14).mean()
    
    # ADX
    df['adx_14'] = 25 + np.random.uniform(-10, 10, n)  # Simplified
    
    # Drop NaN rows
    df = df.dropna()
    
    print(f"Generated {len(df)} days of BANKNIFTY data")
    print(f"Price range: {df['close'].min():.0f} - {df['close'].max():.0f}")
    
    return df


def create_turtle_breakout_strategy():
    """
    Create the classic Turtle Breakout strategy.
    
    Entry: Price breaks above 20-day high
    Exit: Price breaks below 10-day low OR 2% stop loss
    Position Sizing: ATR-based (1% risk per trade)
    """
    print("\nCreating Turtle Breakout strategy...")
    
    strategy = StrategySpec(
        strategy_id="turtle-banknifty-001",
        user_id="demo-user",
        name="Turtle Breakout - BANKNIFTY",
        description="Richard Dennis Turtle Trading System adapted for BANKNIFTY",
        asset_class="equity",
        instruments=["BANKNIFTY"],
        
        # Entry: Simple trend-following (price above 50 EMA)
        entry_rules=[
            EntryRule(
                direction="LONG",
                condition_groups=[
                    ConditionGroup(
                        conditions=[
                            ConditionBlock(
                                left_operand="close",
                                operator=CompareOperator.GREATER,
                                right_operand="ema_50"
                            )
                        ]
                    )
                ]
            )
        ],
        
        # Exit: Stop loss at 2%
        exit_rules=[
            ExitRule(
                exit_type="stop_loss",
                stop_loss_pct=2.0
            )
        ],
        
        # Position sizing: 10% of capital per trade
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=10.0,
            max_position_pct=10.0,
            max_concurrent_positions=1
        ),
        
        # Market filter: Trend-following only
        market_filter=MarketFilter(
            require_above_200ema=False,
            min_adx=None,
            max_vix=None,
            require_positive_breadth=False
        ),
        
        indicators_config={
            "rsi_14": {"period": 14},
            "ema_9": {"period": 9},
            "ema_21": {"period": 21},
            "ema_50": {"period": 50},
            "ema_200": {"period": 200},
            "atr_14": {"period": 14}
        },
        
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=2.0,
        regime_awareness=True,
        status="testing",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    print(f"Strategy: {strategy.name}")
    print(f"Risk per trade: {strategy.risk_per_trade_pct}%")
    print(f"Max daily loss: {strategy.max_daily_loss_pct}%")
    
    return strategy


def configure_backtest(strategy):
    """Configure the backtest parameters"""
    print("\nConfiguring backtest...")
    
    config = BacktestConfig(
        strategy_spec=strategy,
        instrument="BANKNIFTY",
        start_date="2019-01-01",
        end_date="2023-12-31",
        initial_capital=100000.0,  # Rs 1 Lakh
        mode=BacktestMode.VECTORISED,
        
        # Transaction costs (Angel One intraday)
        slippage_value=0.05,  # 0.05% slippage
        brokerage_pct=0.03,   # 0.03% brokerage
        brokerage_fixed=20.0,  # Rs 20 per order
        stt_rate=0.025,       # 0.025% STT
        gst_rate=18.0,        # 18% GST on brokerage
        
        # Validation (disabled for this example)
        run_walk_forward=False,
        run_monte_carlo=False,
        run_regime_analysis=False
    )
    
    print(f"Period: {config.start_date} to {config.end_date}")
    print(f"Initial Capital: Rs {config.initial_capital:,.0f}")
    print(f"Mode: {config.mode}")
    
    return config


def run_backtest(data, strategy, config):
    """Run the backtest"""
    print("\n" + "=" * 60)
    print("RUNNING BACKTEST")
    print("=" * 60)
    
    if not VECTORBT_AVAILABLE:
        print("\n⚠️  vectorbt not installed")
        print("Install with: pip install vectorbt")
        return None
    
    try:
        engine = VectorisedEngine()
        result = engine.run(spec=strategy, data=data, config=config)
        return result
    except Exception as e:
        print(f"\n✗ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_results(result):
    """Analyze and display backtest results"""
    if result is None:
        return
    
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    
    # Performance Summary
    print("\n📊 PERFORMANCE SUMMARY")
    print("-" * 60)
    print(f"Total Return:        {result.total_return_pct:>10.2f}%")
    print(f"CAGR:                {result.cagr_pct:>10.2f}%")
    print(f"Sharpe Ratio:        {result.sharpe_ratio:>10.2f}  {'✓' if result.sharpe_ratio > 1.5 else '⚠️'}")
    print(f"Sortino Ratio:       {result.sortino_ratio:>10.2f}  {'✓' if result.sortino_ratio > 2.0 else '⚠️'}")
    print(f"Calmar Ratio:        {result.calmar_ratio:>10.2f}")
    
    # Risk Metrics
    print("\n⚠️  RISK METRICS")
    print("-" * 60)
    print(f"Max Drawdown:        {result.max_drawdown_pct:>10.2f}%  {'✓' if result.max_drawdown_pct < 15 else '⚠️'}")
    print(f"Avg Drawdown:        {result.avg_drawdown_pct:>10.2f}%")
    print(f"Max DD Duration:     {result.max_drawdown_duration_days:>10} days")
    
    # Trade Statistics
    print("\n📈 TRADE STATISTICS")
    print("-" * 60)
    print(f"Total Trades:        {result.total_trades:>10}")
    print(f"Win Rate:            {result.win_rate_pct:>10.2f}%")
    print(f"Avg Win:             {result.avg_win_pct:>10.2f}%")
    print(f"Avg Loss:            {result.avg_loss_pct:>10.2f}%")
    print(f"Profit Factor:       {result.profit_factor:>10.2f}  {'✓' if result.profit_factor > 1.5 else '⚠️'}")
    print(f"Expectancy:          Rs {result.expectancy_per_trade:>8.2f}")
    print(f"Avg Hold Period:     {result.avg_hold_days:>10.1f} days")
    print(f"Max Consec Losses:   {result.max_consecutive_losses:>10}")
    
    # Position Sizing
    print("\n💰 POSITION SIZING (Kelly Criterion)")
    print("-" * 60)
    print(f"Kelly Fraction:      {result.kelly_fraction:>10.4f} ({result.kelly_fraction * 100:.2f}%)")
    print(f"Half-Kelly:          {result.half_kelly:>10.4f} ({result.half_kelly * 100:.2f}%)")
    
    # Strategy Assessment
    print("\n✅ STRATEGY ASSESSMENT")
    print("-" * 60)
    
    checks = [
        ("Sharpe Ratio > 1.5", result.sharpe_ratio > 1.5),
        ("Sortino Ratio > 2.0", result.sortino_ratio > 2.0),
        ("Max Drawdown < 15%", result.max_drawdown_pct < 15),
        ("Profit Factor > 1.5", result.profit_factor > 1.5),
        ("Positive CAGR", result.cagr_pct > 0),
        ("At least 10 trades", result.total_trades >= 10)
    ]
    
    passed = sum(1 for _, check in checks if check)
    total = len(checks)
    
    for check_name, check_result in checks:
        status = "✓" if check_result else "✗"
        print(f"{status} {check_name}")
    
    print(f"\nScore: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 Excellent! Strategy meets all criteria.")
    elif passed >= total * 0.7:
        print("\n👍 Good! Strategy shows promise but needs refinement.")
    else:
        print("\n⚠️  Warning! Strategy needs significant improvement.")


def main():
    """Main execution"""
    print("=" * 60)
    print("VECTORISED BACKTEST EXAMPLE")
    print("=" * 60)
    
    # Step 1: Generate data
    data = generate_banknifty_sample_data()
    
    # Step 2: Create strategy
    strategy = create_turtle_breakout_strategy()
    
    # Step 3: Configure backtest
    config = configure_backtest(strategy)
    
    # Step 4: Run backtest
    result = run_backtest(data, strategy, config)
    
    # Step 5: Analyze results
    analyze_results(result)
    
    print("\n" + "=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
