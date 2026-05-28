"""
Unit tests for the event-driven backtesting engine.

Tests:
- Gap-fill at gap price (not stop price) when overnight gap exceeds SL
- Slippage models (fixed_pips, pct_spread, market_impact)
- Circuit breaker simulation
- F&O lot-size rounding
- Transaction cost tracking
- Trailing stop loss updates

Requirements: 5.1-5.7
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from services.backtesting.event_engine import EventDrivenEngine, Position
from services.backtesting.models import BacktestConfig, SlippageModel, BacktestMode
from services.algo_builder.models import (
    StrategySpec, EntryRule, ExitRule, PositionSizing,
    MarketFilter, PositionSizingMethod, ConditionGroup, ConditionBlock,
    CompareOperator, LogicGate
)


@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    data = pd.DataFrame({
        'open': np.random.uniform(100, 110, 100),
        'high': np.random.uniform(110, 120, 100),
        'low': np.random.uniform(90, 100, 100),
        'close': np.random.uniform(100, 110, 100),
        'volume': np.random.uniform(1000000, 2000000, 100),
        'rsi_14': np.random.uniform(30, 70, 100),
        'atr_14': np.random.uniform(2, 5, 100),
        'volume_ma_20': np.random.uniform(1000000, 2000000, 100),
    }, index=dates)
    
    return data


@pytest.fixture
def sample_config():
    """Create sample backtest configuration"""
    # Create minimal entry and exit rules
    entry_rule = EntryRule(
        direction='LONG',
        condition_groups=[
            ConditionGroup(
                conditions=[
                    ConditionBlock(
                        left_operand='rsi_14',
                        operator=CompareOperator.GREATER,
                        right_operand=30
                    )
                ],
                gate=LogicGate.AND
            )
        ]
    )
    
    exit_rule = ExitRule(
        exit_type='stop_loss',
        stop_loss_pct=2.0
    )
    
    spec = StrategySpec(
        strategy_id='test_strategy',
        user_id='test_user',
        name='Test Strategy',
        description='Test strategy for event-driven engine',
        asset_class='equity',
        instruments=['BANKNIFTY'],
        entry_rules=[entry_rule],
        exit_rules=[exit_rule],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=10.0,
            max_position_pct=10.0,
            max_concurrent_positions=1
        ),
        market_filter=MarketFilter(),
        indicators_config={},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    config = BacktestConfig(
        strategy_spec=spec,
        instrument='BANKNIFTY',
        start_date='2024-01-01',
        end_date='2024-04-10',
        initial_capital=100000.0,
        mode=BacktestMode.EVENT_DRIVEN,
        slippage_model=SlippageModel.PCT_SPREAD,
        slippage_value=0.05,
        brokerage_pct=0.03,
        brokerage_fixed=20.0,
        stt_rate=0.025,
        gst_rate=18.0
    )
    
    return config



def test_overnight_gap_fill_at_gap_price(sample_config):
    """
    Test that overnight gaps exceeding stop loss fill at gap price, not stop price.
    
    Requirement 5.4: Overnight gap simulation
    """
    engine = EventDrivenEngine()
    
    # Create data with a significant overnight gap
    dates = pd.date_range(start='2024-01-01', periods=5, freq='D')
    data = pd.DataFrame({
        'open': [100, 101, 102, 85, 103],  # Day 4 has gap down to 85
        'high': [105, 106, 107, 90, 108],
        'low': [95, 96, 97, 80, 98],
        'close': [100, 101, 102, 88, 103],
        'volume': [1000000] * 5,
        'rsi_14': [50] * 5,
        'atr_14': [2] * 5,
        'volume_ma_20': [1000000] * 5,
    }, index=dates)
    
    # Manually create a position with stop loss at 95
    position = Position(
        direction='LONG',
        entry_price=100,
        entry_date=dates[0],
        size=100,
        entry_bar_idx=0,
        stop_loss=95,  # Stop loss at 95
        target=110
    )
    
    engine.positions = [position]
    engine.cash = 90000  # Already invested 10000
    engine.initial_capital = 100000
    
    # Process bar 3 (gap down to 85, which is below stop loss of 95)
    prev_bar = data.iloc[2]
    current_bar = data.iloc[3]
    
    # Handle overnight gap
    engine._handle_overnight_gaps(current_bar, prev_bar, sample_config)
    
    # Verify position was closed
    assert len(engine.positions) == 0, "Position should be closed after gap"
    assert len(engine.closed_trades) == 1, "Should have one closed trade"
    
    # Verify exit price is gap open (85), not stop loss (95)
    trade = engine.closed_trades[0]
    assert trade['exit_price'] == 85, f"Exit price should be gap open (85), not stop (95). Got {trade['exit_price']}"
    assert trade['exit_reason'] == 'gap_stop_loss', "Exit reason should be gap_stop_loss"
    
    # Verify P&L reflects gap fill
    expected_pnl = (85 - 100) * 100  # -1500
    assert abs(trade['pnl'] - expected_pnl) < 1, f"P&L should be {expected_pnl}, got {trade['pnl']}"


def test_slippage_fixed_pips(sample_data, sample_config):
    """Test fixed pips slippage model"""
    engine = EventDrivenEngine()
    
    # Configure fixed pips slippage
    sample_config.slippage_model = SlippageModel.FIXED_PIPS
    sample_config.slippage_value = 0.50  # 0.50 price units
    
    bar = sample_data.iloc[0]
    price = 100.0
    size = 100
    
    # Test entry slippage (should add slippage)
    entry_price = engine._apply_slippage(price, size, bar, sample_config, is_entry=True)
    assert entry_price == 100.50, f"Entry price should be 100.50, got {entry_price}"
    
    # Test exit slippage (should subtract slippage)
    exit_price = engine._apply_slippage(price, size, bar, sample_config, is_entry=False)
    assert exit_price == 99.50, f"Exit price should be 99.50, got {exit_price}"


def test_slippage_pct_spread(sample_data, sample_config):
    """Test percentage spread slippage model"""
    engine = EventDrivenEngine()
    
    # Configure pct spread slippage
    sample_config.slippage_model = SlippageModel.PCT_SPREAD
    sample_config.slippage_value = 0.10  # 0.10%
    
    bar = sample_data.iloc[0]
    price = 100.0
    size = 100
    
    # Test entry slippage (should add 0.10%)
    entry_price = engine._apply_slippage(price, size, bar, sample_config, is_entry=True)
    expected_entry = 100.0 * (1 + 0.10 / 100)
    assert abs(entry_price - expected_entry) < 0.01, f"Entry price should be {expected_entry}, got {entry_price}"
    
    # Test exit slippage (should subtract 0.10%)
    exit_price = engine._apply_slippage(price, size, bar, sample_config, is_entry=False)
    expected_exit = 100.0 * (1 - 0.10 / 100)
    assert abs(exit_price - expected_exit) < 0.01, f"Exit price should be {expected_exit}, got {exit_price}"



def test_slippage_market_impact(sample_data, sample_config):
    """Test market impact slippage model"""
    engine = EventDrivenEngine()
    
    # Configure market impact slippage
    sample_config.slippage_model = SlippageModel.MARKET_IMPACT
    sample_config.slippage_value = 0.05  # Base impact factor
    
    bar = sample_data.iloc[0]
    bar['volume_ma_20'] = 1000000
    price = 100.0
    
    # Small order (low impact)
    small_size = 100
    entry_price_small = engine._apply_slippage(price, small_size, bar, sample_config, is_entry=True)
    
    # Large order (high impact)
    large_size = 10000
    entry_price_large = engine._apply_slippage(price, large_size, bar, sample_config, is_entry=True)
    
    # Large order should have more slippage
    assert entry_price_large > entry_price_small, "Large order should have more slippage than small order"


def test_fo_lot_size_rounding():
    """Test F&O lot-size rounding"""
    engine = EventDrivenEngine()
    
    # Test BANKNIFTY (lot size 25)
    size = 73.5  # Should round down to 50 (2 lots)
    rounded = engine._round_to_lot_size(size, 100, 25)
    assert rounded == 50, f"73.5 should round to 50 (2 lots of 25), got {rounded}"
    
    # Test NIFTY (lot size 50)
    size = 123  # Should round down to 100 (2 lots)
    rounded = engine._round_to_lot_size(size, 100, 50)
    assert rounded == 100, f"123 should round to 100 (2 lots of 50), got {rounded}"
    
    # Test edge case: less than 1 lot
    size = 20  # Should round to 0
    rounded = engine._round_to_lot_size(size, 100, 25)
    assert rounded == 0, f"20 should round to 0 (less than 1 lot), got {rounded}"


def test_circuit_breaker_detection(sample_data):
    """Test circuit breaker detection"""
    engine = EventDrivenEngine()
    
    # Create data with circuit breaker event
    dates = pd.date_range(start='2024-01-01', periods=3, freq='D')
    data = pd.DataFrame({
        'open': [100, 101, 94],  # Day 3 opens 6% lower
        'high': [105, 106, 95],
        'low': [95, 96, 90],
        'close': [100, 101, 93],  # Day 3 closes 7.9% lower
        'volume': [1000000] * 3,
    }, index=dates)
    
    # Bar 0: no circuit breaker (first bar)
    assert not engine._is_circuit_breaker_active(data.iloc[0], 0, data)
    
    # Bar 1: no circuit breaker (normal movement)
    assert not engine._is_circuit_breaker_active(data.iloc[1], 1, data)
    
    # Bar 2: circuit breaker (7.9% drop from previous close)
    assert engine._is_circuit_breaker_active(data.iloc[2], 2, data), "Circuit breaker should be active for 7.9% drop"


def test_transaction_costs_tracking(sample_data, sample_config):
    """Test cumulative transaction costs tracking"""
    engine = EventDrivenEngine()
    engine.cash = 100000
    
    trade_value = 10000
    
    # Apply transaction costs
    engine._apply_transaction_costs(trade_value, sample_config)
    
    # Verify costs were calculated
    assert engine.total_brokerage > 0, "Brokerage should be tracked"
    assert engine.total_stt > 0, "STT should be tracked"
    assert engine.total_gst > 0, "GST should be tracked"
    
    # Verify cash was deducted
    expected_brokerage = (sample_config.brokerage_pct / 100) * trade_value + sample_config.brokerage_fixed
    expected_stt = (sample_config.stt_rate / 100) * trade_value
    expected_gst = (sample_config.gst_rate / 100) * expected_brokerage
    expected_total_cost = expected_brokerage + expected_stt + expected_gst
    
    expected_cash = 100000 - expected_total_cost
    assert abs(engine.cash - expected_cash) < 0.01, f"Cash should be {expected_cash}, got {engine.cash}"


def test_trailing_stop_loss_update():
    """Test trailing stop loss updates"""
    dates = pd.date_range(start='2024-01-01', periods=1, freq='D')
    
    # Create LONG position with trailing stop
    position = Position(
        direction='LONG',
        entry_price=100,
        entry_date=dates[0],
        size=100,
        entry_bar_idx=0,
        stop_loss=98,  # Initial stop at 2% below entry
        trailing_sl_pct=2.0  # 2% trailing stop
    )
    
    # Price moves up to 110
    position.update_trailing_stop(110)
    
    # Stop should now be at 110 * 0.98 = 107.8
    expected_stop = 110 * 0.98
    assert abs(position.stop_loss - expected_stop) < 0.01, f"Stop should be {expected_stop}, got {position.stop_loss}"
    
    # Price moves down to 105 (stop should not change)
    old_stop = position.stop_loss
    position.update_trailing_stop(105)
    assert position.stop_loss == old_stop, "Stop should not move down"



def test_full_backtest_run(sample_data, sample_config):
    """Test a complete backtest run"""
    engine = EventDrivenEngine()
    
    # Run backtest (will use simple RSI strategy since no compiled strategy provided)
    result = engine.run(
        spec=sample_config.strategy_spec,
        data=sample_data,
        config=sample_config
    )
    
    # Verify result structure
    assert result.backtest_id is not None
    assert result.mode == BacktestMode.EVENT_DRIVEN
    assert result.instrument == 'BANKNIFTY'
    
    # Verify metrics are calculated
    assert isinstance(result.total_return_pct, float)
    assert isinstance(result.sharpe_ratio, float)
    assert isinstance(result.max_drawdown_pct, float)
    
    # Verify equity curve exists
    assert len(result.equity_curve) > 0, "Equity curve should not be empty"
    
    # Verify final equity matches last equity curve value
    assert result.equity_curve[-1] > 0, "Final equity should be positive"


def test_position_pnl_calculation():
    """Test position P&L calculation"""
    dates = pd.date_range(start='2024-01-01', periods=1, freq='D')
    
    # Test LONG position
    long_position = Position(
        direction='LONG',
        entry_price=100,
        entry_date=dates[0],
        size=100,
        entry_bar_idx=0
    )
    
    # Exit at profit
    pnl, pnl_pct = long_position.calculate_pnl(110)
    assert pnl == 1000, f"LONG P&L should be 1000, got {pnl}"
    assert pnl_pct == 10.0, f"LONG P&L% should be 10%, got {pnl_pct}"
    
    # Exit at loss
    pnl, pnl_pct = long_position.calculate_pnl(95)
    assert pnl == -500, f"LONG P&L should be -500, got {pnl}"
    assert pnl_pct == -5.0, f"LONG P&L% should be -5%, got {pnl_pct}"
    
    # Test SHORT position
    short_position = Position(
        direction='SHORT',
        entry_price=100,
        entry_date=dates[0],
        size=100,
        entry_bar_idx=0
    )
    
    # Exit at profit (price went down)
    pnl, pnl_pct = short_position.calculate_pnl(90)
    assert pnl == 1000, f"SHORT P&L should be 1000, got {pnl}"
    assert pnl_pct == 10.0, f"SHORT P&L% should be 10%, got {pnl_pct}"
    
    # Exit at loss (price went up)
    pnl, pnl_pct = short_position.calculate_pnl(105)
    assert pnl == -500, f"SHORT P&L should be -500, got {pnl}"
    assert pnl_pct == -5.0, f"SHORT P&L% should be -5%, got {pnl_pct}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
