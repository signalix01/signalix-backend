"""Unit tests for BaseStrategy helper methods

Tests all helper methods with known OHLCV data to ensure correct behavior.

Requirements: 3.1, 3.2
"""
import pytest
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data with indicators for testing"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    data = pd.DataFrame({
        'date': dates,
        'open': np.linspace(100, 150, 100),
        'high': np.linspace(105, 155, 100),
        'low': np.linspace(95, 145, 100),
        'close': np.linspace(100, 150, 100),
        'volume': np.random.randint(1000000, 5000000, 100),
    })
    
    # Add some indicators for testing
    data['rsi_14'] = np.linspace(30, 70, 100)  # RSI trending from 30 to 70
    data['ema_9'] = np.linspace(98, 148, 100)
    data['ema_21'] = np.linspace(100, 150, 100)
    data['sma_50'] = np.linspace(99, 149, 100)
    data['atr_14'] = np.full(100, 2.5)
    
    return data


@pytest.fixture
def crossover_data():
    """Create data specifically for testing crossover scenarios"""
    data = pd.DataFrame({
        'open': [100] * 10,
        'high': [105] * 10,
        'low': [95] * 10,
        'close': [100, 101, 102, 103, 104, 105, 104, 103, 102, 101],
        'volume': [1000000] * 10,
        'ema_9': [102, 103, 104, 105, 106, 107, 106, 105, 104, 103],  # Fast EMA
        'ema_21': [104, 104, 104, 104, 104, 104, 104, 104, 104, 104],  # Slow EMA (flat)
        'rsi_14': [25, 28, 32, 35, 40, 45, 50, 55, 60, 65],  # RSI trending up
    })
    return data


@pytest.fixture
def data_with_nans():
    """Create data with NaN values to test edge cases"""
    data = pd.DataFrame({
        'open': [100, 101, 102, 103, 104],
        'high': [105, 106, 107, 108, 109],
        'low': [95, 96, 97, 98, 99],
        'close': [100, 101, 102, 103, 104],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        'rsi_14': [np.nan, np.nan, 45, 50, 55],  # First 2 values are NaN
        'ema_9': [np.nan, 100, 101, 102, 103],   # First value is NaN
    })
    return data


class ConcreteStrategy(BaseStrategy):
    """Concrete implementation of BaseStrategy for testing"""
    
    def compute_indicators(self):
        """No-op for testing"""
        pass
    
    def market_filter_pass(self, bar_idx: int) -> bool:
        """Simple filter: always pass"""
        return True
    
    def should_enter_long(self, bar_idx: int) -> bool:
        """Simple entry: RSI < 30"""
        rsi = self.get_value('rsi_14', bar_idx)
        return rsi is not None and rsi < 30
    
    def should_enter_short(self, bar_idx: int) -> bool:
        """Simple entry: RSI > 70"""
        rsi = self.get_value('rsi_14', bar_idx)
        return rsi is not None and rsi > 70
    
    def should_exit(self, position, bar_idx: int):
        """Simple exit: always False for testing"""
        return False, ""
    
    def position_size(self, capital: float, price: float, atr: float) -> float:
        """Simple sizing: 1% of capital"""
        return capital * 0.01


# ============================================================================
# Test: BaseStrategy Initialization
# ============================================================================

def test_init_success(sample_ohlcv_data):
    """Test successful initialization with valid data"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    assert strategy.capital == 100000.0
    assert strategy.initial_capital == 100000.0
    assert len(strategy.data) == 100
    assert 'close' in strategy.data.columns


def test_init_empty_data():
    """Test initialization fails with empty data"""
    empty_data = pd.DataFrame()
    
    with pytest.raises(ValueError, match="Data cannot be None or empty"):
        ConcreteStrategy(empty_data, 100000.0)


def test_init_none_data():
    """Test initialization fails with None data"""
    with pytest.raises(ValueError, match="Data cannot be None or empty"):
        ConcreteStrategy(None, 100000.0)


def test_init_missing_ohlcv_columns():
    """Test initialization fails when required OHLCV columns are missing"""
    incomplete_data = pd.DataFrame({
        'open': [100, 101, 102],
        'close': [100, 101, 102],
        # Missing: high, low, volume
    })
    
    with pytest.raises(ValueError, match="Data missing required columns"):
        ConcreteStrategy(incomplete_data, 100000.0)


# ============================================================================
# Test: get_value() Helper Method
# ============================================================================

def test_get_value_success(sample_ohlcv_data):
    """Test getting indicator values successfully"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # Test getting close price
    close_val = strategy.get_value('close', 50)
    assert close_val is not None
    assert isinstance(close_val, float)
    assert close_val == pytest.approx(125.0, rel=0.1)
    
    # Test getting RSI
    rsi_val = strategy.get_value('rsi_14', 50)
    assert rsi_val is not None
    assert rsi_val == pytest.approx(50.0, rel=0.1)


def test_get_value_first_bar(sample_ohlcv_data):
    """Test getting value from first bar (index 0)"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    close_val = strategy.get_value('close', 0)
    assert close_val is not None
    assert close_val == pytest.approx(100.0, rel=0.1)


def test_get_value_last_bar(sample_ohlcv_data):
    """Test getting value from last bar"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    close_val = strategy.get_value('close', 99)
    assert close_val is not None
    assert close_val == pytest.approx(150.0, rel=0.1)


def test_get_value_invalid_index(sample_ohlcv_data):
    """Test getting value with invalid bar index returns None"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # Negative index
    assert strategy.get_value('close', -1) is None
    
    # Index beyond data length
    assert strategy.get_value('close', 1000) is None


def test_get_value_nonexistent_indicator(sample_ohlcv_data):
    """Test getting value for non-existent indicator returns None"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    assert strategy.get_value('nonexistent_indicator', 50) is None


def test_get_value_with_nan(data_with_nans):
    """Test getting NaN values returns None"""
    strategy = ConcreteStrategy(data_with_nans, 100000.0)
    
    # First RSI value is NaN
    assert strategy.get_value('rsi_14', 0) is None
    
    # Third RSI value is valid
    rsi_val = strategy.get_value('rsi_14', 2)
    assert rsi_val is not None
    assert rsi_val == 45.0


# ============================================================================
# Test: crosses_above() Helper Method
# ============================================================================

def test_crosses_above_indicator_vs_indicator(crossover_data):
    """Test crosses_above with two indicators"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # At index 3: ema_9 (105) crosses above ema_21 (104)
    # Previous: ema_9[2]=104, ema_21[2]=104 (equal, so ema_9 was not above)
    # Current: ema_9[3]=105, ema_21[3]=104 (ema_9 is now above)
    assert strategy.crosses_above('ema_9', 'ema_21', 3) is True
    
    # At index 2: ema_9 (104) equals ema_21 (104), no cross
    assert strategy.crosses_above('ema_9', 'ema_21', 2) is False
    
    # At index 6: ema_9 (106) crosses below ema_21 (104), not above
    assert strategy.crosses_above('ema_9', 'ema_21', 6) is False


def test_crosses_above_indicator_vs_value(crossover_data):
    """Test crosses_above with indicator vs numeric value"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # RSI crosses above 30 at some point
    # At index 2: rsi[1]=28 < 30, rsi[2]=32 >= 30 → crosses above
    assert strategy.crosses_above('rsi_14', 30, 2) is True
    
    # At index 1: rsi[0]=25 < 30, rsi[1]=28 < 30 → no cross
    assert strategy.crosses_above('rsi_14', 30, 1) is False
    
    # At index 5: rsi already above 30, no new cross
    assert strategy.crosses_above('rsi_14', 30, 5) is False


def test_crosses_above_first_bar(crossover_data):
    """Test crosses_above at first bar (index 0) returns False"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # Cannot detect crossover at index 0 (no previous bar)
    assert strategy.crosses_above('ema_9', 'ema_21', 0) is False


def test_crosses_above_with_nan(data_with_nans):
    """Test crosses_above with NaN values returns False"""
    strategy = ConcreteStrategy(data_with_nans, 100000.0)
    
    # Index 1: rsi_14[0]=NaN, rsi_14[1]=NaN → cannot detect cross
    assert strategy.crosses_above('rsi_14', 40, 1) is False
    
    # Index 2: rsi_14[1]=NaN, rsi_14[2]=45 → cannot detect cross (prev is NaN)
    assert strategy.crosses_above('rsi_14', 40, 2) is False


def test_crosses_above_nonexistent_indicator(crossover_data):
    """Test crosses_above with non-existent indicator returns False"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    assert strategy.crosses_above('nonexistent', 'ema_21', 5) is False
    assert strategy.crosses_above('ema_9', 'nonexistent', 5) is False


def test_crosses_above_exact_equality():
    """Test crosses_above handles exact equality correctly"""
    data = pd.DataFrame({
        'open': [100] * 5,
        'high': [105] * 5,
        'low': [95] * 5,
        'close': [100] * 5,
        'volume': [1000000] * 5,
        'indicator_a': [49, 50, 51, 52, 53],
        'indicator_b': [50, 50, 50, 50, 50],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # At index 1: a[0]=49 < b[0]=50, a[1]=50 >= b[1]=50 → crosses above
    assert strategy.crosses_above('indicator_a', 'indicator_b', 1) is True
    
    # At index 2: a[1]=50 >= b[1]=50 (already at or above), no new cross
    assert strategy.crosses_above('indicator_a', 'indicator_b', 2) is False


# ============================================================================
# Test: crosses_below() Helper Method
# ============================================================================

def test_crosses_below_indicator_vs_indicator(crossover_data):
    """Test crosses_below with two indicators"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # At index 6: ema_9 (106) crosses below ema_21 (104)
    # Wait, looking at data: ema_9 goes 102,103,104,105,106,107,106,105,104,103
    # ema_21 is flat at 104
    # At index 5: ema_9[4]=106 > ema_21[4]=104, ema_9[5]=107 > ema_21[5]=104 (no cross)
    # At index 6: ema_9[5]=107 > ema_21[5]=104, ema_9[6]=106 > ema_21[6]=104 (no cross yet)
    # Actually ema_9 never crosses below ema_21 in this data
    
    # Let's check if ema_9 crosses below at index 8
    # At index 8: ema_9[7]=105 > ema_21[7]=104, ema_9[8]=104 <= ema_21[8]=104 → crosses below
    assert strategy.crosses_below('ema_9', 'ema_21', 8) is True
    
    # At index 3: ema_9 crosses above, not below
    assert strategy.crosses_below('ema_9', 'ema_21', 3) is False


def test_crosses_below_indicator_vs_value(crossover_data):
    """Test crosses_below with indicator vs numeric value"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # close goes: 100, 101, 102, 103, 104, 105, 104, 103, 102, 101
    # At index 6: close[5]=105 > 104, close[6]=104 <= 104 → crosses below 104
    assert strategy.crosses_below('close', 104, 6) is True
    
    # At index 5: close[4]=104 <= 104, close[5]=105 > 104 → crosses above, not below
    assert strategy.crosses_below('close', 104, 5) is False


def test_crosses_below_first_bar(crossover_data):
    """Test crosses_below at first bar (index 0) returns False"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # Cannot detect crossover at index 0 (no previous bar)
    assert strategy.crosses_below('ema_9', 'ema_21', 0) is False


def test_crosses_below_with_nan(data_with_nans):
    """Test crosses_below with NaN values returns False"""
    strategy = ConcreteStrategy(data_with_nans, 100000.0)
    
    # Index 1: ema_9[0]=NaN, ema_9[1]=100 → cannot detect cross (prev is NaN)
    assert strategy.crosses_below('ema_9', 101, 1) is False


def test_crosses_below_nonexistent_indicator(crossover_data):
    """Test crosses_below with non-existent indicator returns False"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    assert strategy.crosses_below('nonexistent', 'ema_21', 5) is False
    assert strategy.crosses_below('ema_9', 'nonexistent', 5) is False


def test_crosses_below_exact_equality():
    """Test crosses_below handles exact equality correctly"""
    data = pd.DataFrame({
        'open': [100] * 5,
        'high': [105] * 5,
        'low': [95] * 5,
        'close': [100] * 5,
        'volume': [1000000] * 5,
        'indicator_a': [53, 52, 51, 50, 49],
        'indicator_b': [50, 50, 50, 50, 50],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # At index 3: a[2]=51 > b[2]=50, a[3]=50 <= b[3]=50 → crosses below
    assert strategy.crosses_below('indicator_a', 'indicator_b', 3) is True
    
    # At index 4: a[3]=50 <= b[3]=50 (already at or below), no new cross
    assert strategy.crosses_below('indicator_a', 'indicator_b', 4) is False


# ============================================================================
# Test: between() Helper Method
# ============================================================================

def test_between_success(sample_ohlcv_data):
    """Test between with value in range"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # RSI at index 50 should be around 50, which is between 40 and 60
    assert strategy.between('rsi_14', (40, 60), 50) is True
    
    # RSI at index 10 should be around 34, which is NOT between 40 and 60
    assert strategy.between('rsi_14', (40, 60), 10) is False


def test_between_boundary_values(sample_ohlcv_data):
    """Test between with values exactly at boundaries (inclusive)"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # RSI at index 0 is 30, should be between 30 and 70 (inclusive)
    assert strategy.between('rsi_14', (30, 70), 0) is True
    
    # RSI at index 99 is 70, should be between 30 and 70 (inclusive)
    assert strategy.between('rsi_14', (30, 70), 99) is True


def test_between_outside_range(sample_ohlcv_data):
    """Test between with value outside range"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # RSI at index 0 is 30, NOT between 40 and 60
    assert strategy.between('rsi_14', (40, 60), 0) is False
    
    # RSI at index 99 is 70, NOT between 40 and 60
    assert strategy.between('rsi_14', (40, 60), 99) is False


def test_between_invalid_bounds(sample_ohlcv_data):
    """Test between with invalid bounds returns False"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # Single value instead of tuple
    assert strategy.between('rsi_14', 50, 50) is False
    
    # Three values instead of two
    assert strategy.between('rsi_14', (30, 50, 70), 50) is False
    
    # Empty tuple
    assert strategy.between('rsi_14', (), 50) is False


def test_between_with_nan(data_with_nans):
    """Test between with NaN values returns False"""
    strategy = ConcreteStrategy(data_with_nans, 100000.0)
    
    # Index 0: rsi_14 is NaN
    assert strategy.between('rsi_14', (40, 60), 0) is False
    
    # Index 2: rsi_14 is 45, which is between 40 and 60
    assert strategy.between('rsi_14', (40, 60), 2) is True


def test_between_nonexistent_indicator(sample_ohlcv_data):
    """Test between with non-existent indicator returns False"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    assert strategy.between('nonexistent', (40, 60), 50) is False


def test_between_inverted_bounds(sample_ohlcv_data):
    """Test between with inverted bounds (upper < lower)"""
    strategy = ConcreteStrategy(sample_ohlcv_data, 100000.0)
    
    # Bounds are (60, 40) instead of (40, 60)
    # RSI at index 50 is ~50, which is NOT between 60 and 40
    assert strategy.between('rsi_14', (60, 40), 50) is False


# ============================================================================
# Test: Integration - Using Helper Methods Together
# ============================================================================

def test_integration_entry_logic(crossover_data):
    """Test using multiple helper methods together for entry logic"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # Complex entry condition: EMA cross AND RSI in range
    for bar_idx in range(1, len(crossover_data)):
        ema_cross = strategy.crosses_above('ema_9', 'ema_21', bar_idx)
        rsi_in_range = strategy.between('rsi_14', (30, 50), bar_idx)
        
        if ema_cross and rsi_in_range:
            # At index 3: ema_9 crosses above ema_21, and rsi_14=35 (in range 30-50)
            assert bar_idx == 3


def test_integration_exit_logic(crossover_data):
    """Test using multiple helper methods together for exit logic"""
    strategy = ConcreteStrategy(crossover_data, 100000.0)
    
    # Exit condition: EMA cross below OR RSI above 60
    for bar_idx in range(1, len(crossover_data)):
        ema_cross_below = strategy.crosses_below('ema_9', 'ema_21', bar_idx)
        rsi_val = strategy.get_value('rsi_14', bar_idx)
        rsi_above_60 = rsi_val is not None and rsi_val > 60
        
        if ema_cross_below or rsi_above_60:
            # Should trigger at index 8 (ema cross below) or index 9 (rsi > 60)
            assert bar_idx in [8, 9]


# ============================================================================
# Test: Edge Cases
# ============================================================================

def test_edge_case_single_bar():
    """Test with single bar of data"""
    data = pd.DataFrame({
        'open': [100],
        'high': [105],
        'low': [95],
        'close': [100],
        'volume': [1000000],
        'rsi_14': [50],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # get_value should work
    assert strategy.get_value('rsi_14', 0) == 50.0
    
    # crosses_above/below should return False (need at least 2 bars)
    assert strategy.crosses_above('rsi_14', 40, 0) is False
    assert strategy.crosses_below('rsi_14', 60, 0) is False
    
    # between should work
    assert strategy.between('rsi_14', (40, 60), 0) is True


def test_edge_case_all_nan_indicator():
    """Test with indicator that is all NaN"""
    data = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 106, 107],
        'low': [95, 96, 97],
        'close': [100, 101, 102],
        'volume': [1000000, 1100000, 1200000],
        'bad_indicator': [np.nan, np.nan, np.nan],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # All operations should return None/False
    assert strategy.get_value('bad_indicator', 1) is None
    assert strategy.crosses_above('bad_indicator', 50, 1) is False
    assert strategy.crosses_below('bad_indicator', 50, 1) is False
    assert strategy.between('bad_indicator', (40, 60), 1) is False


def test_edge_case_zero_values():
    """Test with zero values (valid but edge case)"""
    data = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 106, 107],
        'low': [95, 96, 97],
        'close': [100, 101, 102],
        'volume': [1000000, 1100000, 1200000],
        'indicator': [0, 0, 1],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # get_value should return 0.0
    assert strategy.get_value('indicator', 0) == 0.0
    
    # crosses_above from 0 to 1
    assert strategy.crosses_above('indicator', 0, 2) is True
    
    # between with 0
    assert strategy.between('indicator', (-1, 1), 0) is True


def test_edge_case_negative_values():
    """Test with negative indicator values"""
    data = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 106, 107],
        'low': [95, 96, 97],
        'close': [100, 101, 102],
        'volume': [1000000, 1100000, 1200000],
        'indicator': [-10, -5, 0],
    })
    strategy = ConcreteStrategy(data, 100000.0)
    
    # get_value should return negative values
    assert strategy.get_value('indicator', 0) == -10.0
    
    # crosses_above with negative values
    assert strategy.crosses_above('indicator', -7, 1) is True
    
    # between with negative bounds
    assert strategy.between('indicator', (-15, -3), 0) is True
