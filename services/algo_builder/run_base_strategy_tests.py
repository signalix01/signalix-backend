"""
Simple test runner for BaseStrategy class
Runs unit tests without requiring pytest
"""
import sys
import os
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy


# ============================================================================
# Concrete Strategy Implementation for Testing
# ============================================================================

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
# Test Data Fixtures
# ============================================================================

def create_sample_ohlcv_data():
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


def create_crossover_data():
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


def create_data_with_nans():
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


# ============================================================================
# Test Functions
# ============================================================================

def test_init_success():
    """Test successful initialization with valid data"""
    print("\n1. Testing successful initialization...")
    try:
        data = create_sample_ohlcv_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        assert strategy.capital == 100000.0, "Capital mismatch"
        assert strategy.initial_capital == 100000.0, "Initial capital mismatch"
        assert len(strategy.data) == 100, "Data length mismatch"
        assert 'close' in strategy.data.columns, "Missing close column"
        
        print("✓ Initialization successful")
        return True
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        traceback.print_exc()
        return False


def test_init_validation():
    """Test initialization validation"""
    print("\n2. Testing initialization validation...")
    try:
        # Test empty data
        try:
            empty_data = pd.DataFrame()
            ConcreteStrategy(empty_data, 100000.0)
            print("✗ Should have rejected empty data")
            return False
        except ValueError:
            print("✓ Correctly rejected empty data")
        
        # Test missing columns
        try:
            incomplete_data = pd.DataFrame({
                'open': [100, 101, 102],
                'close': [100, 101, 102],
            })
            ConcreteStrategy(incomplete_data, 100000.0)
            print("✗ Should have rejected incomplete data")
            return False
        except ValueError:
            print("✓ Correctly rejected incomplete data")
        
        return True
    except Exception as e:
        print(f"✗ Validation test failed: {e}")
        traceback.print_exc()
        return False


def test_get_value():
    """Test get_value helper method"""
    print("\n3. Testing get_value() helper...")
    try:
        data = create_sample_ohlcv_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # Test getting close price
        close_val = strategy.get_value('close', 50)
        assert close_val is not None, "get_value returned None"
        assert abs(close_val - 125.0) < 1.0, f"Close value mismatch: {close_val}"
        
        # Test getting RSI
        rsi_val = strategy.get_value('rsi_14', 50)
        assert rsi_val is not None, "RSI value is None"
        assert abs(rsi_val - 50.0) < 1.0, f"RSI value mismatch: {rsi_val}"
        
        # Test invalid index
        assert strategy.get_value('close', -1) is None, "Should return None for negative index"
        assert strategy.get_value('close', 1000) is None, "Should return None for out of bounds"
        
        # Test non-existent indicator
        assert strategy.get_value('nonexistent', 50) is None, "Should return None for non-existent"
        
        print("✓ get_value() works correctly")
        return True
    except Exception as e:
        print(f"✗ get_value() test failed: {e}")
        traceback.print_exc()
        return False


def test_get_value_with_nan():
    """Test get_value with NaN values"""
    print("\n4. Testing get_value() with NaN...")
    try:
        data = create_data_with_nans()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # First RSI value is NaN
        assert strategy.get_value('rsi_14', 0) is None, "Should return None for NaN"
        
        # Third RSI value is valid
        rsi_val = strategy.get_value('rsi_14', 2)
        assert rsi_val is not None, "Valid RSI should not be None"
        assert rsi_val == 45.0, f"RSI value mismatch: {rsi_val}"
        
        print("✓ get_value() handles NaN correctly")
        return True
    except Exception as e:
        print(f"✗ get_value() NaN test failed: {e}")
        traceback.print_exc()
        return False


def test_crosses_above():
    """Test crosses_above helper method"""
    print("\n5. Testing crosses_above()...")
    try:
        data = create_crossover_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # At index 3: ema_9 (105) crosses above ema_21 (104)
        assert strategy.crosses_above('ema_9', 'ema_21', 3) is True, "Should detect cross above at index 3"
        
        # At index 2: no cross
        assert strategy.crosses_above('ema_9', 'ema_21', 2) is False, "Should not detect cross at index 2"
        
        # Test with numeric value: RSI crosses above 30
        assert strategy.crosses_above('rsi_14', 30, 2) is True, "Should detect RSI cross above 30"
        
        # Test at first bar (should return False)
        assert strategy.crosses_above('ema_9', 'ema_21', 0) is False, "Should return False at index 0"
        
        print("✓ crosses_above() works correctly")
        return True
    except Exception as e:
        print(f"✗ crosses_above() test failed: {e}")
        traceback.print_exc()
        return False


def test_crosses_below():
    """Test crosses_below helper method"""
    print("\n6. Testing crosses_below()...")
    try:
        data = create_crossover_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # At index 8: ema_9 (104) crosses below ema_21 (104)
        assert strategy.crosses_below('ema_9', 'ema_21', 8) is True, "Should detect cross below at index 8"
        
        # Test with numeric value: close crosses below 104
        assert strategy.crosses_below('close', 104, 6) is True, "Should detect close cross below 104"
        
        # Test at first bar (should return False)
        assert strategy.crosses_below('ema_9', 'ema_21', 0) is False, "Should return False at index 0"
        
        print("✓ crosses_below() works correctly")
        return True
    except Exception as e:
        print(f"✗ crosses_below() test failed: {e}")
        traceback.print_exc()
        return False


def test_between():
    """Test between helper method"""
    print("\n7. Testing between()...")
    try:
        data = create_sample_ohlcv_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # RSI at index 50 should be around 50, which is between 40 and 60
        assert strategy.between('rsi_14', (40, 60), 50) is True, "RSI should be between 40 and 60"
        
        # RSI at index 10 should be around 34, which is NOT between 40 and 60
        assert strategy.between('rsi_14', (40, 60), 10) is False, "RSI should not be between 40 and 60"
        
        # Test boundary values (inclusive)
        assert strategy.between('rsi_14', (30, 70), 0) is True, "Should include lower boundary"
        assert strategy.between('rsi_14', (30, 70), 99) is True, "Should include upper boundary"
        
        # Test invalid bounds
        assert strategy.between('rsi_14', 50, 50) is False, "Should reject non-tuple bounds"
        
        print("✓ between() works correctly")
        return True
    except Exception as e:
        print(f"✗ between() test failed: {e}")
        traceback.print_exc()
        return False


def test_crossover_edge_cases():
    """Test crossover methods with edge cases"""
    print("\n8. Testing crossover edge cases...")
    try:
        data = create_data_with_nans()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # Test with NaN values
        assert strategy.crosses_above('rsi_14', 40, 1) is False, "Should return False with NaN"
        assert strategy.crosses_below('ema_9', 101, 1) is False, "Should return False with NaN"
        
        # Test with non-existent indicators
        assert strategy.crosses_above('nonexistent', 'ema_9', 2) is False, "Should return False for non-existent"
        assert strategy.crosses_below('ema_9', 'nonexistent', 2) is False, "Should return False for non-existent"
        
        print("✓ Crossover edge cases handled correctly")
        return True
    except Exception as e:
        print(f"✗ Crossover edge case test failed: {e}")
        traceback.print_exc()
        return False


def test_integration_entry_logic():
    """Test using multiple helper methods together"""
    print("\n9. Testing integration with entry logic...")
    try:
        data = create_crossover_data()
        strategy = ConcreteStrategy(data, 100000.0)
        
        # Complex entry condition: EMA cross AND RSI in range
        found_entry = False
        for bar_idx in range(1, len(data)):
            ema_cross = strategy.crosses_above('ema_9', 'ema_21', bar_idx)
            rsi_in_range = strategy.between('rsi_14', (30, 50), bar_idx)
            
            if ema_cross and rsi_in_range:
                # At index 3: ema_9 crosses above ema_21, and rsi_14=35 (in range 30-50)
                assert bar_idx == 3, f"Expected entry at index 3, got {bar_idx}"
                found_entry = True
                break
        
        assert found_entry, "Should have found entry signal"
        
        print("✓ Integration test passed")
        return True
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        traceback.print_exc()
        return False


def test_edge_case_single_bar():
    """Test with single bar of data"""
    print("\n10. Testing single bar edge case...")
    try:
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
        assert strategy.get_value('rsi_14', 0) == 50.0, "get_value should work with single bar"
        
        # crosses_above/below should return False (need at least 2 bars)
        assert strategy.crosses_above('rsi_14', 40, 0) is False, "crosses_above should return False"
        assert strategy.crosses_below('rsi_14', 60, 0) is False, "crosses_below should return False"
        
        # between should work
        assert strategy.between('rsi_14', (40, 60), 0) is True, "between should work with single bar"
        
        print("✓ Single bar edge case handled correctly")
        return True
    except Exception as e:
        print(f"✗ Single bar test failed: {e}")
        traceback.print_exc()
        return False


def test_edge_case_zero_and_negative():
    """Test with zero and negative values"""
    print("\n11. Testing zero and negative values...")
    try:
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
        assert strategy.get_value('indicator', 0) == -10.0, "Should handle negative values"
        
        # crosses_above with negative values
        assert strategy.crosses_above('indicator', -7, 1) is True, "Should detect cross above with negatives"
        
        # between with negative bounds
        assert strategy.between('indicator', (-15, -3), 0) is True, "Should handle negative bounds"
        
        print("✓ Zero and negative values handled correctly")
        return True
    except Exception as e:
        print(f"✗ Zero/negative test failed: {e}")
        traceback.print_exc()
        return False


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all tests"""
    print("=" * 60)
    print("BaseStrategy Class - Unit Test Suite")
    print("=" * 60)
    
    tests = [
        ("Initialization Success", test_init_success),
        ("Initialization Validation", test_init_validation),
        ("get_value() Method", test_get_value),
        ("get_value() with NaN", test_get_value_with_nan),
        ("crosses_above() Method", test_crosses_above),
        ("crosses_below() Method", test_crosses_below),
        ("between() Method", test_between),
        ("Crossover Edge Cases", test_crossover_edge_cases),
        ("Integration Test", test_integration_entry_logic),
        ("Single Bar Edge Case", test_edge_case_single_bar),
        ("Zero/Negative Values", test_edge_case_zero_and_negative),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            traceback.print_exc()
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
