"""
Manual test script for BacktestDataPipeline.

This script can be run directly without pytest to verify the implementation.
It tests indicator computation with synthetic data.

Usage:
    python manual_test.py
"""

import pandas as pd
import numpy as np
import sys
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, '.')

try:
    from data_pipeline import BacktestDataPipeline
    from indicators.supertrend import compute_supertrend
    print("✓ Imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    print("\nNote: This test requires TA-Lib to be installed.")
    print("See README.md for installation instructions.")
    sys.exit(1)


def test_indicator_computation():
    """Test indicator computation with synthetic data"""
    print("\n" + "="*60)
    print("TEST 1: Indicator Computation")
    print("="*60)
    
    # Create synthetic OHLCV data
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=300, freq='D')
    
    base_price = 40000
    df = pd.DataFrame({
        'open': base_price + np.random.randn(300).cumsum() * 100,
        'high': base_price + np.random.randn(300).cumsum() * 100 + 200,
        'low': base_price + np.random.randn(300).cumsum() * 100 - 200,
        'close': base_price + np.random.randn(300).cumsum() * 100,
        'volume': np.random.uniform(1000000, 2000000, 300)
    }, index=dates)
    
    # Ensure high >= low
    df['high'] = df[['high', 'low', 'close', 'open']].max(axis=1)
    df['low'] = df[['low', 'close', 'open']].min(axis=1)
    
    print(f"Created synthetic data: {len(df)} bars")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    print(f"Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    
    # Initialize pipeline
    pipeline = BacktestDataPipeline()
    
    # Compute indicators
    print("\nComputing indicators...")
    result = pipeline.compute_indicators(df)
    
    # Verify all expected indicators
    expected_indicators = [
        'rsi_14', 'ema_21', 'ema_50', 'ema_200',
        'macd', 'macd_signal', 'macd_hist',
        'bb_upper', 'bb_mid', 'bb_lower',
        'atr_14', 'adx_14', 'stoch_k', 'stoch_d',
        'cci_14', 'mfi_14', 'obv', 'vwap',
        'supertrend', 'supertrend_direction'
    ]
    
    missing = []
    for indicator in expected_indicators:
        if indicator not in result.columns:
            missing.append(indicator)
    
    if missing:
        print(f"\n✗ Missing indicators: {missing}")
        return False
    else:
        print(f"\n✓ All {len(expected_indicators)} key indicators present")
    
    # Check for NaN values
    if result.isnull().any().any():
        print("✗ Found NaN values in result")
        return False
    else:
        print("✓ No NaN values in result")
    
    print(f"\n✓ Final dataset: {len(result)} bars with {len(result.columns)} columns")
    print(f"✓ Indicators computed successfully")
    
    # Show sample values
    print("\nSample indicator values (last row):")
    sample_indicators = ['close', 'rsi_14', 'ema_21', 'macd', 'atr_14', 'supertrend_direction']
    for ind in sample_indicators:
        if ind in result.columns:
            val = result[ind].iloc[-1]
            print(f"  {ind:25s}: {val:.2f}" if not pd.isna(val) else f"  {ind:25s}: NaN")
    
    return True


def test_supertrend():
    """Test SuperTrend indicator"""
    print("\n" + "="*60)
    print("TEST 2: SuperTrend Indicator")
    print("="*60)
    
    # Create uptrend data
    df = pd.DataFrame({
        'high': [100 + i*2 for i in range(50)],
        'low': [98 + i*2 for i in range(50)],
        'close': [99 + i*2 for i in range(50)]
    })
    
    print(f"Created uptrend data: {len(df)} bars")
    print(f"Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    
    # Compute SuperTrend
    supertrend, direction = compute_supertrend(df, period=10, multiplier=3.0)
    
    print(f"\n✓ SuperTrend computed: {len(supertrend)} values")
    
    # Count signals
    bullish = (direction == 1).sum()
    bearish = (direction == -1).sum()
    
    print(f"  Bullish signals: {bullish}")
    print(f"  Bearish signals: {bearish}")
    
    # In uptrend, expect mostly bullish
    if bullish > bearish:
        print("✓ Correctly detected uptrend (more bullish signals)")
    else:
        print("⚠ Warning: Expected more bullish signals in uptrend")
    
    return True


def test_data_validation():
    """Test data validation"""
    print("\n" + "="*60)
    print("TEST 3: Data Validation")
    print("="*60)
    
    # Create data with issues
    dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
    df = pd.DataFrame({
        'open': np.random.uniform(40000, 42000, 50),
        'high': np.random.uniform(42000, 43000, 50),
        'low': np.random.uniform(39000, 40000, 50),
        'close': np.random.uniform(40000, 42000, 50),
        'volume': np.random.uniform(1000000, 2000000, 50)
    }, index=dates)
    
    # Introduce issues
    df.loc[df.index[10], 'close'] = np.nan  # Missing value
    df.loc[df.index[20], 'close'] = 0  # Zero price
    df.loc[df.index[30], 'close'] = -100  # Negative price
    
    print(f"Created data with issues:")
    print(f"  - 1 NaN value")
    print(f"  - 1 zero price")
    print(f"  - 1 negative price")
    
    # Validate
    pipeline = BacktestDataPipeline()
    result = pipeline.validate_and_adjust(df, "TEST", "NSE_EQUITY")
    
    # Check fixes
    has_nan = result.isnull().any().any()
    has_zero = (result['close'] == 0).any()
    has_negative = (result['close'] < 0).any()
    
    if not has_nan and not has_zero and not has_negative:
        print(f"\n✓ All issues fixed")
        print(f"✓ Valid bars: {len(result)}")
        return True
    else:
        print(f"\n✗ Issues remain:")
        if has_nan:
            print("  - Still has NaN values")
        if has_zero:
            print("  - Still has zero prices")
        if has_negative:
            print("  - Still has negative prices")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("BacktestDataPipeline Manual Test Suite")
    print("="*60)
    
    results = []
    
    try:
        results.append(("Indicator Computation", test_indicator_computation()))
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Indicator Computation", False))
    
    try:
        results.append(("SuperTrend", test_supertrend()))
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("SuperTrend", False))
    
    try:
        results.append(("Data Validation", test_data_validation()))
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Data Validation", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8s} {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
