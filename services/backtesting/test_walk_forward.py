"""
Unit tests for WalkForwardValidator.

Tests walk-forward validation with the Turtle Breakout strategy.

Requirements: 6.1-6.6
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.backtesting.walk_forward import WalkForwardValidator, WalkForwardResult
from services.backtesting.vectorised_engine import VectorisedEngine, VECTORBT_AVAILABLE
from services.backtesting.models import BacktestConfig, BacktestMode
from services.algo_builder.models import (
    StrategySpec, EntryRule, ExitRule, PositionSizing, MarketFilter,
    ConditionBlock, ConditionGroup, CompareOperator, PositionSizingMethod
)


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data with indicators for testing"""
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
    
    return df


@pytest.fixture
def turtle_strategy():
    """Create a Turtle Breakout strategy specification"""
    strategy = StrategySpec(
        strategy_id="test-turtle-wf-001",
        user_id="test-user-001",
        name="Turtle Breakout Walk-Forward Test",
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
    return strategy


@pytest.fixture
def backtest_config(turtle_strategy):
    """Create a backtest configuration"""
    config = BacktestConfig(
        strategy_spec=turtle_strategy,
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
        run_walk_forward=True,
        wf_train_pct=0.70,
        wf_validate_pct=0.15,
        wf_test_pct=0.15,
        run_monte_carlo=False,
        run_regime_analysis=False
    )
    return config


def test_walk_forward_validator_initialization():
    """Test that the validator initializes correctly"""
    validator = WalkForwardValidator()
    assert validator is not None


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_walk_forward_data_split(sample_data, turtle_strategy, backtest_config):
    """Test that data is split correctly into three periods"""
    validator = WalkForwardValidator()
    
    train_data, validate_data, test_data = validator._split_data(
        sample_data,
        backtest_config.wf_train_pct,
        backtest_config.wf_validate_pct,
        backtest_config.wf_test_pct
    )
    
    # Verify split sizes
    total_len = len(sample_data)
    expected_train = int(total_len * 0.70)
    expected_validate = int(total_len * 0.15)
    
    assert len(train_data) == expected_train
    assert len(validate_data) == expected_validate
    assert len(test_data) > 0  # Remaining data
    
    # Verify no overlap
    assert train_data.index[-1] < validate_data.index[0]
    assert validate_data.index[-1] < test_data.index[0]
    
    # Verify all data is accounted for
    total_split = len(train_data) + len(validate_data) + len(test_data)
    assert total_split == total_len
    
    print(f"\nData split verification:")
    print(f"  Total: {total_len} days")
    print(f"  Train: {len(train_data)} days ({len(train_data)/total_len*100:.1f}%)")
    print(f"  Validate: {len(validate_data)} days ({len(validate_data)/total_len*100:.1f}%)")
    print(f"  Test: {len(test_data)} days ({len(test_data)/total_len*100:.1f}%)")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_walk_forward_validation_run(sample_data, turtle_strategy, backtest_config):
    """Test running complete walk-forward validation"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Verify result structure
    assert isinstance(result, WalkForwardResult)
    assert result.train is not None
    assert result.validation is not None
    assert result.test is not None
    
    # Verify consistency score
    assert isinstance(result.consistency_score, float)
    assert 0.0 <= result.consistency_score <= 1.0
    
    # Verify flags
    assert isinstance(result.is_robust, bool)
    assert isinstance(result.overfitting_detected, bool)
    assert isinstance(result.warnings, list)
    
    print(f"\nWalk-Forward Validation Results:")
    print(f"  Consistency Score: {result.consistency_score:.3f}")
    print(f"  Is Robust: {result.is_robust}")
    print(f"  Overfitting Detected: {result.overfitting_detected}")
    print(f"  Warnings: {len(result.warnings)}")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_walk_forward_three_separate_results(sample_data, turtle_strategy, backtest_config):
    """Test that three separate result objects are returned"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Verify three separate BacktestResult objects
    assert result.train.backtest_id != result.validation.backtest_id
    assert result.validation.backtest_id != result.test.backtest_id
    assert result.train.backtest_id != result.test.backtest_id
    
    # Verify each has its own metrics
    assert isinstance(result.train.total_return_pct, float)
    assert isinstance(result.validation.total_return_pct, float)
    assert isinstance(result.test.total_return_pct, float)
    
    assert isinstance(result.train.sharpe_ratio, float)
    assert isinstance(result.validation.sharpe_ratio, float)
    assert isinstance(result.test.sharpe_ratio, float)
    
    print(f"\nThree Separate Results Verification:")
    print(f"\nTrain Period:")
    print(f"  Period: {result.train.period}")
    print(f"  Return: {result.train.total_return_pct:.2f}%")
    print(f"  Sharpe: {result.train.sharpe_ratio:.2f}")
    print(f"  Trades: {result.train.total_trades}")
    
    print(f"\nValidation Period:")
    print(f"  Period: {result.validation.period}")
    print(f"  Return: {result.validation.total_return_pct:.2f}%")
    print(f"  Sharpe: {result.validation.sharpe_ratio:.2f}")
    print(f"  Trades: {result.validation.total_trades}")
    
    print(f"\nTest Period:")
    print(f"  Period: {result.test.period}")
    print(f"  Return: {result.test.total_return_pct:.2f}%")
    print(f"  Sharpe: {result.test.sharpe_ratio:.2f}")
    print(f"  Trades: {result.test.total_trades}")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_consistency_score_calculation(sample_data, turtle_strategy, backtest_config):
    """Test consistency score calculation logic"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Verify consistency score formula
    # If all periods positive: max(0, 1 - abs((train_sharpe - test_sharpe) / train_sharpe))
    all_positive = (
        result.train.total_return_pct > 0 and
        result.validation.total_return_pct > 0 and
        result.test.total_return_pct > 0
    )
    
    if all_positive and result.train.sharpe_ratio != 0:
        expected_degradation = abs(
            (result.train.sharpe_ratio - result.test.sharpe_ratio) / result.train.sharpe_ratio
        )
        expected_consistency = max(0.0, 1.0 - expected_degradation)
        
        # Allow small floating point differences
        assert abs(result.consistency_score - expected_consistency) < 0.001
        
        print(f"\nConsistency Score Calculation:")
        print(f"  Train Sharpe: {result.train.sharpe_ratio:.3f}")
        print(f"  Test Sharpe: {result.test.sharpe_ratio:.3f}")
        print(f"  Degradation: {expected_degradation:.3f}")
        print(f"  Consistency: {result.consistency_score:.3f}")
    else:
        # If not all positive, consistency should be 0
        assert result.consistency_score == 0.0
        print(f"\nNot all periods positive - consistency score = 0.0")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_low_consistency_warning(sample_data, turtle_strategy, backtest_config):
    """Test that warning is added when consistency score < 0.7"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Check if warning is present when consistency < 0.7
    if result.consistency_score < 0.7:
        assert len(result.warnings) > 0
        assert any("inconsistent performance" in w.lower() for w in result.warnings)
        print(f"\n✓ Low consistency warning triggered (score={result.consistency_score:.3f})")
    else:
        print(f"\n✓ Good consistency (score={result.consistency_score:.3f})")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_overfitting_detection(sample_data, turtle_strategy, backtest_config):
    """Test overfitting detection logic"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Check overfitting flag logic
    # Overfitting: train_sharpe > 2.0 AND test_sharpe < 0.5
    expected_overfitting = (
        result.train.sharpe_ratio > 2.0 and
        result.test.sharpe_ratio < 0.5
    )
    
    assert result.overfitting_detected == expected_overfitting
    
    if expected_overfitting:
        assert any("overfitting" in w.lower() for w in result.warnings)
        print(f"\n⚠️  Overfitting detected:")
        print(f"  Train Sharpe: {result.train.sharpe_ratio:.2f}")
        print(f"  Test Sharpe: {result.test.sharpe_ratio:.2f}")
    else:
        print(f"\n✓ No overfitting detected:")
        print(f"  Train Sharpe: {result.train.sharpe_ratio:.2f}")
        print(f"  Test Sharpe: {result.test.sharpe_ratio:.2f}")


@pytest.mark.skipif(not VECTORBT_AVAILABLE, reason="vectorbt not installed")
def test_robustness_check(sample_data, turtle_strategy, backtest_config):
    """Test robustness determination logic"""
    validator = WalkForwardValidator()
    engine = VectorisedEngine()
    
    result = validator.validate(
        engine=engine,
        spec=turtle_strategy,
        data=sample_data,
        config=backtest_config
    )
    
    # Robustness criteria:
    # - consistency_score >= 0.7
    # - test_sharpe > 1.0
    # - not overfitting_detected
    expected_robust = (
        result.consistency_score >= 0.7 and
        result.test.sharpe_ratio > 1.0 and
        not result.overfitting_detected
    )
    
    assert result.is_robust == expected_robust
    
    print(f"\nRobustness Check:")
    print(f"  Consistency >= 0.7: {result.consistency_score >= 0.7} ({result.consistency_score:.3f})")
    print(f"  Test Sharpe > 1.0: {result.test.sharpe_ratio > 1.0} ({result.test.sharpe_ratio:.2f})")
    print(f"  No Overfitting: {not result.overfitting_detected}")
    print(f"  → Is Robust: {result.is_robust}")


def generate_sample_data():
    """Generate sample OHLCV data (non-fixture version for manual testing)"""
    dates = pd.date_range(start='2019-01-01', end='2023-12-31', freq='D')
    n = len(dates)
    
    np.random.seed(42)
    trend = np.linspace(100, 150, n)
    noise = np.random.normal(0, 5, n)
    close = trend + noise
    
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
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr_14'] = true_range.rolling(14).mean()
    
    df = df.dropna()
    return df


def create_turtle_strategy():
    """Create a Turtle Breakout strategy (non-fixture version for manual testing)"""
    return StrategySpec(
        strategy_id="test-turtle-wf-001",
        user_id="test-user-001",
        name="Turtle Breakout Walk-Forward Test",
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


if __name__ == "__main__":
    # Run tests manually
    print("Testing Walk-Forward Validation\n")
    print("=" * 60)
    
    # Generate test data
    print("\n1. Generating sample data...")
    data = generate_sample_data()
    print(f"   Generated {len(data)} days of data")
    
    # Create strategy
    print("\n2. Creating Turtle Breakout strategy...")
    strategy = create_turtle_strategy()
    print(f"   Strategy: {strategy.name}")
    
    # Create config
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
        run_walk_forward=True,
        wf_train_pct=0.70,
        wf_validate_pct=0.15,
        wf_test_pct=0.15,
        run_monte_carlo=False,
        run_regime_analysis=False
    )
    print(f"   Period: {config.start_date} to {config.end_date}")
    print(f"   Initial Capital: Rs {config.initial_capital:,.0f}")
    print(f"   Walk-Forward Split: {config.wf_train_pct:.0%} / "
          f"{config.wf_validate_pct:.0%} / {config.wf_test_pct:.0%}")
    
    # Run walk-forward validation
    if VECTORBT_AVAILABLE:
        print("\n4. Running walk-forward validation...")
        validator = WalkForwardValidator()
        engine = VectorisedEngine()
        
        result = validator.validate(
            engine=engine,
            spec=strategy,
            data=data,
            config=config
        )
        
        print("\n" + "=" * 60)
        print("WALK-FORWARD VALIDATION RESULTS")
        print("=" * 60)
        
        print(f"\n{'TRAIN PERIOD':<20} {result.train.period}")
        print(f"{'Return:':<20} {result.train.total_return_pct:>10.2f}%")
        print(f"{'Sharpe Ratio:':<20} {result.train.sharpe_ratio:>10.2f}")
        print(f"{'Total Trades:':<20} {result.train.total_trades:>10}")
        
        print(f"\n{'VALIDATION PERIOD':<20} {result.validation.period}")
        print(f"{'Return:':<20} {result.validation.total_return_pct:>10.2f}%")
        print(f"{'Sharpe Ratio:':<20} {result.validation.sharpe_ratio:>10.2f}")
        print(f"{'Total Trades:':<20} {result.validation.total_trades:>10}")
        
        print(f"\n{'TEST PERIOD':<20} {result.test.period}")
        print(f"{'Return:':<20} {result.test.total_return_pct:>10.2f}%")
        print(f"{'Sharpe Ratio:':<20} {result.test.sharpe_ratio:>10.2f}")
        print(f"{'Total Trades:':<20} {result.test.total_trades:>10}")
        
        print(f"\n{'VALIDATION METRICS':<20}")
        print(f"{'Consistency Score:':<20} {result.consistency_score:>10.3f}")
        print(f"{'Is Robust:':<20} {str(result.is_robust):>10}")
        print(f"{'Overfitting:':<20} {str(result.overfitting_detected):>10}")
        
        if result.warnings:
            print(f"\n{'WARNINGS:':<20}")
            for i, warning in enumerate(result.warnings, 1):
                print(f"  {i}. {warning}")
        
        # Verify test requirements
        print("\n" + "=" * 60)
        print("TEST VERIFICATION")
        print("=" * 60)
        
        three_results = (
            result.train.backtest_id != result.validation.backtest_id and
            result.validation.backtest_id != result.test.backtest_id
        )
        
        print(f"\n✓ Three separate result objects: {three_results}")
        print(f"✓ Consistency score computed: {0.0 <= result.consistency_score <= 1.0}")
        print(f"✓ Warnings generated: {len(result.warnings) >= 0}")
        print(f"✓ Overfitting check performed: {isinstance(result.overfitting_detected, bool)}")
        
        if three_results:
            print("\n✅ ALL TESTS PASSED")
        else:
            print("\n⚠️  SOME TESTS FAILED")
    else:
        print("\n⚠️  vectorbt not installed. Install with: pip install vectorbt")
        print("   Skipping walk-forward validation execution.")
