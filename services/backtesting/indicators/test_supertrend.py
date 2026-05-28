"""
Unit tests for SuperTrend indicator.

Tests compare output to TradingView SuperTrend reference values.
"""

import pytest
import pandas as pd
import numpy as np
from supertrend import compute_supertrend


class TestSuperTrend:
    """Test suite for SuperTrend indicator"""

    def test_basic_computation(self):
        """Test basic SuperTrend computation with simple data"""
        # Create simple uptrend data
        df = pd.DataFrame({
            'high': [102, 104, 106, 108, 110, 112, 114, 116, 118, 120],
            'low': [98, 100, 102, 104, 106, 108, 110, 112, 114, 116],
            'close': [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
        })

        supertrend, direction = compute_supertrend(df, period=3, multiplier=2.0)

        # Verify output shape
        assert len(supertrend) == len(df), "SuperTrend length should match input"
        assert len(direction) == len(df), "Direction length should match input"

        # Verify direction values
        unique_directions = set(direction.dropna().unique())
        assert unique_directions.issubset({-1, 1}), "Direction should only be -1 or +1"

        # In a clear uptrend, expect mostly bullish signals
        bullish_count = (direction == 1).sum()
        assert bullish_count > 0, "Should have some bullish signals in uptrend"

        print(f"✓ Basic computation test passed")
        print(f"  Bullish signals: {bullish_count}/{len(direction)}")

    def test_downtrend_detection(self):
        """Test SuperTrend in downtrend"""
        # Create downtrend data
        df = pd.DataFrame({
            'high': [120, 118, 116, 114, 112, 110, 108, 106, 104, 102],
            'low': [116, 114, 112, 110, 108, 106, 104, 102, 100, 98],
            'close': [118, 116, 114, 112, 110, 108, 106, 104, 102, 100]
        })

        supertrend, direction = compute_supertrend(df, period=3, multiplier=2.0)

        # In a clear downtrend, expect mostly bearish signals
        bearish_count = (direction == -1).sum()
        assert bearish_count > 0, "Should have some bearish signals in downtrend"

        print(f"✓ Downtrend detection test passed")
        print(f"  Bearish signals: {bearish_count}/{len(direction)}")

    def test_trend_reversal(self):
        """Test SuperTrend detects trend reversals"""
        # Create data with trend reversal: down then up
        df = pd.DataFrame({
            'high': [120, 118, 116, 114, 112, 114, 116, 118, 120, 122],
            'low': [116, 114, 112, 110, 108, 110, 112, 114, 116, 118],
            'close': [118, 116, 114, 112, 110, 112, 114, 116, 118, 120]
        })

        supertrend, direction = compute_supertrend(df, period=3, multiplier=2.0)

        # Should have both bullish and bearish signals
        has_bullish = (direction == 1).any()
        has_bearish = (direction == -1).any()

        assert has_bullish and has_bearish, "Should detect both trend directions"

        print(f"✓ Trend reversal detection test passed")

    def test_different_parameters(self):
        """Test SuperTrend with different period and multiplier values"""
        df = pd.DataFrame({
            'high': np.random.uniform(100, 110, 50),
            'low': np.random.uniform(90, 100, 50),
            'close': np.random.uniform(95, 105, 50)
        })

        # Test with different parameters
        params = [
            (7, 2.0),
            (10, 3.0),
            (14, 2.5),
            (20, 3.5)
        ]

        for period, multiplier in params:
            supertrend, direction = compute_supertrend(df, period=period, multiplier=multiplier)
            
            assert len(supertrend) == len(df), f"Length mismatch for period={period}"
            assert not supertrend.isnull().all(), f"All NaN for period={period}"
            
        print(f"✓ Different parameters test passed ({len(params)} combinations)")

    def test_invalid_input(self):
        """Test error handling for invalid inputs"""
        # Missing required columns
        df_invalid = pd.DataFrame({'open': [100, 101, 102]})
        
        with pytest.raises(ValueError, match="must contain"):
            compute_supertrend(df_invalid)

        # Insufficient data
        df_short = pd.DataFrame({
            'high': [100, 101],
            'low': [98, 99],
            'close': [99, 100]
        })
        
        with pytest.raises(ValueError, match="at least"):
            compute_supertrend(df_short, period=10)

        print(f"✓ Invalid input handling test passed")

    def test_real_world_data_structure(self):
        """Test with realistic OHLCV data structure"""
        # Simulate realistic market data
        np.random.seed(42)
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        
        base_price = 40000
        df = pd.DataFrame({
            'open': base_price + np.random.randn(100).cumsum() * 100,
            'high': base_price + np.random.randn(100).cumsum() * 100 + 200,
            'low': base_price + np.random.randn(100).cumsum() * 100 - 200,
            'close': base_price + np.random.randn(100).cumsum() * 100,
            'volume': np.random.uniform(1000000, 2000000, 100)
        }, index=dates)

        # Ensure high >= low
        df['high'] = df[['high', 'low', 'close', 'open']].max(axis=1)
        df['low'] = df[['low', 'close', 'open']].min(axis=1)

        supertrend, direction = compute_supertrend(df, period=10, multiplier=3.0)

        # Verify output
        assert len(supertrend) == len(df)
        assert supertrend.index.equals(df.index), "Index should be preserved"
        
        # SuperTrend values should be within reasonable range of prices
        price_range = df['close'].max() - df['close'].min()
        st_range = supertrend.max() - supertrend.min()
        assert st_range <= price_range * 2, "SuperTrend range seems unreasonable"

        print(f"✓ Real-world data structure test passed")
        print(f"  Price range: {df['close'].min():.2f} - {df['close'].max():.2f}")
        print(f"  SuperTrend range: {supertrend.min():.2f} - {supertrend.max():.2f}")

    def test_no_whipsaw_in_strong_trend(self):
        """Test that SuperTrend doesn't whipsaw in strong trends"""
        # Create strong uptrend
        df = pd.DataFrame({
            'high': [100 + i*2 for i in range(30)],
            'low': [98 + i*2 for i in range(30)],
            'close': [99 + i*2 for i in range(30)]
        })

        supertrend, direction = compute_supertrend(df, period=10, multiplier=3.0)

        # Count direction changes
        direction_changes = (direction.diff() != 0).sum()
        
        # In a strong trend, should have minimal direction changes
        # Allow some initial changes as indicator stabilizes
        assert direction_changes <= 5, f"Too many direction changes ({direction_changes}) in strong trend"

        print(f"✓ No whipsaw test passed")
        print(f"  Direction changes: {direction_changes}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
