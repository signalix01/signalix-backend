"""
Simple test runner for VectorisedEngine without pytest dependency.

This script tests the vectorised backtesting engine with sample data.
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from services.backtesting.vectorised_engine import VectorisedEngine, VECTORBT_AVAILABLE
    from services.backtesting.models import BacktestConfig, BacktestMode
    from services.algo_builder.models import (
        StrategySpec, EntryRule, ExitRule, PositionSizing, MarketFilter,
        ConditionBlock, ConditionGroup, CompareOperator, PositionSizingMethod
    )
    
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)


def generate_sample_data():
    """Generate sample OHLCV data with indicators for testing"""
    print("\n1. Generating sample data...")
    
    # Generate 5 years of daily data
    dates = pd.date_range(start='2019-01-01', end='2023-12-31', freq='D')
    n = len(dates)
    
    # Generate realistic price data with trend and noise
    np.random.seed(42)
    trend = np.linspace(100, 150, n)
    noise = np.random.normal(0, 5, n)
    close = trend + noise
    
    # Generate OHLC from close
    high = close + np.random.uniform(0, 3, n)
    low = close - np.random.uniform(0, 3, n)
    open_price = close + np.random.uniform(-2, 2, n)
    volume = np.random.uniform(1000000, 5000000, n)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    # Add indicators
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # EMAs
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr_14'] = true_range.rolling(14).mean()
    
    # Drop NaN rows
    df = df.dropna()
    
    print(f"   Generated {len(df)} days of data")
    return df


def create_turtle_strategy():
    """Create a Turtle Breakout strategy specification"""
    print("\n2. Creating Turtle Breakout strategy...")
    
    strategy = StrategySpec(
        strategy_id="test-turtle-001",
        user_id="test-user-001",
        name="Turtle Breakout Test",
        description="20-day channel breakout with 10-day channel stop",
        asset_class="equity",
        instruments=["BANKNIFTY"],
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
        exit_rules=[
            ExitRule(
                exit_type="stop_loss",
                stop_loss_pct=2.0
            )
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=10.0,
            max_position_pct=10.0,
            max_concurrent_positions=1
        ),
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
            "ema_200": {"period": 200}
        },
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=2.0,
        regime_awareness=True,
        status="testing",
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )
    
    print(f"   Strategy: {strategy.name}")
    return strategy


def create_backtest_config(strategy):
    """Create a backtest configuration"""
    print("\n3. Creating backtest configuration...")
    
    config = BacktestConfig(
        strategy_spec=strategy,
        instrument="BANKNIFTY",
        start_date="2019-01-01",
        end_date="2023-12-31",
        initial_capital=100000.0,
        mode=BacktestMode.VECTORISED,
        slippage_value=0.05,
        brokerage_pct=0.03,
        brokerage_fixed=20.0,
        stt_rate=0.025,
        gst_rate=18.0,
        run_walk_forward=False,
        run_monte_carlo=False,
        run_regime_analysis=False
    )
    
    print(f"   Period: {config.start_date} to {config.end_date}")
    print(f"   Initial Capital: Rs {config.initial_capital:,.0f}")
    return config


def run_backtest(data, strategy, config):
    """Run the backtest"""
    print("\n4. Running vectorised backtest...")
    
    if not VECTORBT_AVAILABLE:
        print("\n⚠️  vectorbt not installed. Install with: pip install vectorbt")
        print("   Skipping backtest execution.")
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


def print_results(result):
    """Print backtest results"""
    if result is None:
        return
    
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"\nPerformance Metrics:")
    print(f"  Total Return:     {result.total_return_pct:>10.2f}%")
    print(f"  CAGR:             {result.cagr_pct:>10.2f}%")
    print(f"  Sharpe Ratio:     {result.sharpe_ratio:>10.2f}")
    print(f"  Sortino Ratio:    {result.sortino_ratio:>10.2f}")
    print(f"  Calmar Ratio:     {result.calmar_ratio:>10.2f}")
    print(f"  Max Drawdown:     {result.max_drawdown_pct:>10.2f}%")
    
    print(f"\nTrade Statistics:")
    print(f"  Total Trades:     {result.total_trades:>10}")
    print(f"  Win Rate:         {result.win_rate_pct:>10.2f}%")
    print(f"  Avg Win:          {result.avg_win_pct:>10.2f}%")
    print(f"  Avg Loss:         {result.avg_loss_pct:>10.2f}%")
    print(f"  Profit Factor:    {result.profit_factor:>10.2f}")
    print(f"  Expectancy:       Rs {result.expectancy_per_trade:>8.2f}")
    print(f"  Avg Hold Days:    {result.avg_hold_days:>10.1f}")
    print(f"  Max Consec Loss:  {result.max_consecutive_losses:>10}")
    
    print(f"\nRisk Metrics:")
    print(f"  Kelly Fraction:   {result.kelly_fraction:>10.4f}")
    print(f"  Half-Kelly:       {result.half_kelly:>10.4f}")


def verify_requirements(result):
    """Verify test requirements"""
    if result is None:
        return False
    
    print("\n" + "=" * 60)
    print("TEST VERIFICATION")
    print("=" * 60)
    
    sharpe_positive = result.sharpe_ratio > 0
    trades_non_empty = result.total_trades > 0
    
    print(f"\n✓ Sharpe > 0: {sharpe_positive} (Sharpe = {result.sharpe_ratio:.2f})")
    print(f"✓ Trade list non-empty: {trades_non_empty} ({result.total_trades} trades)")
    
    if sharpe_positive and trades_non_empty:
        print("\n✅ ALL TESTS PASSED")
        return True
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return False


def main():
    """Main test execution"""
    print("Testing Vectorised Backtesting Engine")
    print("=" * 60)
    
    # Generate test data
    data = generate_sample_data()
    
    # Create strategy
    strategy = create_turtle_strategy()
    
    # Create config
    config = create_backtest_config(strategy)
    
    # Run backtest
    result = run_backtest(data, strategy, config)
    
    # Print results
    print_results(result)
    
    # Verify requirements
    success = verify_requirements(result)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
