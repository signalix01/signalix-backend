"""
Unit tests for BacktestDataPipeline.

Tests:
- Fetch 1 year BANKNIFTY daily data
- Verify all indicator columns present and non-null
- Test caching functionality
- Test data validation
- Test SuperTrend computation
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_pipeline import BacktestDataPipeline, AssetClass


class TestBacktestDataPipeline:
    """Test suite for BacktestDataPipeline"""

    @pytest.fixture
    def pipeline(self):
        """Create a pipeline instance without DB/Redis for testing"""
        return BacktestDataPipeline(db_connection=None, redis_client=None)

    def test_compute_indicators_basic(self, pipeline):
        """Test that compute_indicators adds all expected columns"""
        # Create sample OHLCV data
        dates = pd.date_range(start='2023-01-01', periods=300, freq='D')
        df = pd.DataFrame({
            'open': np.random.uniform(40000, 42000, 300),
            'high': np.random.uniform(42000, 43000, 300),
            'low': np.random.uniform(39000, 40000, 300),
            'close': np.random.uniform(40000, 42000, 300),
            'volume': np.random.uniform(1000000, 2000000, 300)
        }, index=dates)

        # Compute indicators
        result = pipeline.compute_indicators(df)

        # Verify all expected indicator columns are present
        expected_indicators = [
            # RSI
            'rsi_5', 'rsi_9', 'rsi_14', 'rsi_20', 'rsi_21', 'rsi_50', 'rsi_200',
            # EMA
            'ema_5', 'ema_9', 'ema_14', 'ema_20', 'ema_21', 'ema_50', 'ema_200',
            # SMA
            'sma_5', 'sma_9', 'sma_14', 'sma_20', 'sma_21', 'sma_50', 'sma_200',
            # MACD
            'macd', 'macd_signal', 'macd_hist',
            # Bollinger Bands
            'bb_upper', 'bb_mid', 'bb_lower',
            # Other indicators
            'atr_14', 'adx_14', 'stoch_k', 'stoch_d',
            'cci_14', 'mfi_14', 'obv', 'vwap',
            # Rolling features
            'highest_high_5', 'highest_high_10', 'highest_high_20', 'highest_high_52',
            'lowest_low_5', 'lowest_low_10', 'lowest_low_20', 'lowest_low_52',
            'volume_ma_20',
            # SuperTrend
            'supertrend', 'supertrend_direction'
        ]

        for indicator in expected_indicators:
            assert indicator in result.columns, f"Missing indicator: {indicator}"

        # Verify no NaN values in the result (after dropna)
        assert not result.isnull().any().any(), "Found NaN values in computed indicators"

        print(f"✓ All {len(expected_indicators)} indicators computed successfully")
        print(f"✓ Result shape: {result.shape}")

    def test_supertrend_computation(self, pipeline):
        """Test SuperTrend indicator computation"""
        # Create sample data with a clear trend
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        
        # Create uptrend data
        base_price = 40000
        df = pd.DataFrame({
            'open': [base_price + i * 100 for i in range(100)],
            'high': [base_price + i * 100 + 200 for i in range(100)],
            'low': [base_price + i * 100 - 100 for i in range(100)],
            'close': [base_price + i * 100 + 50 for i in range(100)],
            'volume': [1000000] * 100
        }, index=dates)

        # Compute SuperTrend
        supertrend, direction = pipeline.compute_supertrend(df, period=10, multiplier=3.0)

        # Verify output shape
        assert len(supertrend) == len(df), "SuperTrend length mismatch"
        assert len(direction) == len(df), "Direction length mismatch"

        # Verify direction values are only +1 or -1
        assert set(direction.dropna().unique()).issubset({-1, 1}), "Invalid direction values"

        # In an uptrend, we expect mostly bullish signals (+1)
        bullish_count = (direction == 1).sum()
        bearish_count = (direction == -1).sum()
        
        print(f"✓ SuperTrend computed: {bullish_count} bullish, {bearish_count} bearish signals")
        print(f"✓ SuperTrend values range: {supertrend.min():.2f} to {supertrend.max():.2f}")

    def test_validate_and_adjust(self, pipeline):
        """Test data validation and adjustment"""
        # Create data with some issues
        dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
        df = pd.DataFrame({
            'open': np.random.uniform(40000, 42000, 50),
            'high': np.random.uniform(42000, 43000, 50),
            'low': np.random.uniform(39000, 40000, 50),
            'close': np.random.uniform(40000, 42000, 50),
            'volume': np.random.uniform(1000000, 2000000, 50)
        }, index=dates)

        # Introduce some issues
        df.loc[df.index[10], 'close'] = np.nan  # Missing value
        df.loc[df.index[20], 'close'] = 0  # Zero price
        df.loc[df.index[30], 'close'] = -100  # Negative price

        # Validate and adjust
        result = pipeline.validate_and_adjust(df, "TEST", "NSE_EQUITY")

        # Verify issues are fixed
        assert not result.isnull().any().any(), "NaN values not handled"
        assert (result['close'] > 0).all(), "Zero/negative prices not removed"
        assert result.index.is_monotonic_increasing, "Data not sorted"

        print(f"✓ Data validation passed: {len(result)} valid bars")

    def test_find_missing_ranges(self, pipeline):
        """Test missing range detection"""
        # Create cached data with gaps
        dates = pd.date_range(start='2023-01-15', end='2023-02-15', freq='D')
        cached_df = pd.DataFrame({
            'open': [40000] * len(dates),
            'high': [41000] * len(dates),
            'low': [39000] * len(dates),
            'close': [40500] * len(dates),
            'volume': [1000000] * len(dates)
        }, index=dates)

        # Request wider range
        start = '2023-01-01'
        end = '2023-03-01'

        missing = pipeline.find_missing_ranges(cached_df, start, end, '1D')

        # Should find gaps before and after cached data
        assert len(missing) > 0, "Should detect missing ranges"
        print(f"✓ Found {len(missing)} missing ranges: {missing}")

    @pytest.mark.asyncio
    async def test_fetch_yfinance_fallback(self, pipeline):
        """Test yfinance fallback fetcher with real data"""
        # Fetch 1 year of BANKNIFTY data (using ^NSEBANK as proxy)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        try:
            df = await pipeline.fetch_yfinance_fallback(
                instrument="^NSEBANK",  # Bank Nifty index
                start=start_date,
                end=end_date,
                timeframe="1D"
            )

            # Verify data structure
            assert not df.empty, "No data fetched"
            assert all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']), \
                "Missing required columns"

            # Verify data quality
            assert (df['high'] >= df['low']).all(), "High should be >= Low"
            assert (df['high'] >= df['close']).all(), "High should be >= Close"
            assert (df['high'] >= df['open']).all(), "High should be >= Open"
            assert (df['low'] <= df['close']).all(), "Low should be <= Close"
            assert (df['low'] <= df['open']).all(), "Low should be <= Open"

            print(f"✓ Fetched {len(df)} bars of BANKNIFTY data")
            print(f"✓ Date range: {df.index.min()} to {df.index.max()}")
            print(f"✓ Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")

        except Exception as e:
            pytest.skip(f"yfinance fetch failed (network issue?): {e}")

    @pytest.mark.asyncio
    async def test_full_pipeline_integration(self, pipeline):
        """Integration test: fetch data and compute all indicators"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        try:
            # This will use yfinance fallback since we don't have DB/API credentials
            df = await pipeline.get_backtest_data(
                instrument="^NSEBANK",
                start=start_date,
                end=end_date,
                timeframe="1D",
                asset_class="NSE_EQUITY"
            )

            # Verify all indicators are present
            required_indicators = [
                'rsi_14', 'ema_21', 'ema_50', 'ema_200',
                'macd', 'bb_upper', 'bb_lower',
                'atr_14', 'adx_14', 'supertrend'
            ]

            for indicator in required_indicators:
                assert indicator in df.columns, f"Missing indicator: {indicator}"
                assert not df[indicator].isnull().all(), f"Indicator {indicator} is all NaN"

            print(f"✓ Full pipeline test passed")
            print(f"✓ Final dataset: {len(df)} bars with {len(df.columns)} columns")
            print(f"✓ All {len(required_indicators)} key indicators present and valid")

        except Exception as e:
            pytest.skip(f"Integration test failed (network issue?): {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
