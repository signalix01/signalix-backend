"""
Unit tests for market regime analyzer.

Requirements: 8.1–8.4
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from services.backtesting.regime_analyzer import (
    RegimeAnalyzer,
    RegimeType,
    RegimeAnalysisResult,
    RegimeRecommendation
)


class TestRegimeAnalyzer:
    """Test suite for RegimeAnalyzer"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = RegimeAnalyzer()
    
    def create_test_data(self, n_days: int = 500) -> pd.DataFrame:
        """Create synthetic OHLCV data with indicators"""
        dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')
        
        # Create synthetic price data
        np.random.seed(42)
        close_prices = 100 + np.cumsum(np.random.randn(n_days) * 2)
        
        df = pd.DataFrame({
            'close': close_prices,
            'high': close_prices * 1.02,
            'low': close_prices * 0.98,
            'open': close_prices * 0.99,
            'volume': np.random.randint(1000000, 5000000, n_days),
        }, index=dates)
        
        # Add indicators
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['adx_14'] = np.random.uniform(15, 40, n_days)  # Simplified ADX
        df['atr_14'] = df['close'] * 0.02  # 2% ATR
        
        return df
    
    def create_vix_data(self, dates: pd.DatetimeIndex, vix_level: float = 20.0) -> pd.DataFrame:
        """Create synthetic VIX data"""
        return pd.DataFrame({
            'close': [vix_level] * len(dates)
        }, index=dates)
    
    def test_classify_regimes_all_types(self):
        """Test that all 5 regime types can be classified"""
        # Create data spanning 2 years to ensure all regimes appear
        df = self.create_test_data(n_days=730)
        
        # Create VIX data with varying levels
        vix_values = []
        for i in range(730):
            if i < 146:  # First 20%: low VIX
                vix_values.append(15.0)
            elif i < 292:  # Next 20%: moderate VIX
                vix_values.append(22.0)
            elif i < 438:  # Next 20%: high VIX
                vix_values.append(30.0)
            elif i < 584:  # Next 20%: crisis VIX
                vix_values.append(40.0)
            else:  # Last 20%: back to low
                vix_values.append(16.0)
        
        vix_data = pd.DataFrame({'close': vix_values}, index=df.index)
        
        # Classify regimes
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # Verify all 5 regime types are present
        unique_regimes = set(regimes.unique())
        assert RegimeType.TRENDING_BULL in unique_regimes or RegimeType.TRENDING_BEAR in unique_regimes
        assert RegimeType.VOLATILE in unique_regimes
        assert RegimeType.CRISIS in unique_regimes
        assert RegimeType.RANGING in unique_regimes
        
        # Verify regimes series has same length as input
        assert len(regimes) == len(df)
    
    def test_classify_regimes_trending_bull(self):
        """Test classification of trending bull regime"""
        df = self.create_test_data(n_days=100)
        
        # Force trending bull conditions
        df['close'] = df['ema_200'] * 1.1  # Price above EMA
        df['adx_14'] = 30.0  # Strong trend
        
        vix_data = self.create_vix_data(df.index, vix_level=15.0)  # Low VIX
        
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # Most days should be trending_bull
        assert (regimes == RegimeType.TRENDING_BULL).sum() > 50
    
    def test_classify_regimes_trending_bear(self):
        """Test classification of trending bear regime"""
        df = self.create_test_data(n_days=100)
        
        # Force trending bear conditions
        df['close'] = df['ema_200'] * 0.9  # Price below EMA
        df['adx_14'] = 30.0  # Strong trend
        
        vix_data = self.create_vix_data(df.index, vix_level=20.0)  # Moderate VIX
        
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # Most days should be trending_bear
        assert (regimes == RegimeType.TRENDING_BEAR).sum() > 50
    
    def test_classify_regimes_volatile(self):
        """Test classification of volatile regime"""
        df = self.create_test_data(n_days=100)
        
        vix_data = self.create_vix_data(df.index, vix_level=30.0)  # High VIX
        
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # All days should be volatile
        assert (regimes == RegimeType.VOLATILE).sum() == 100
    
    def test_classify_regimes_crisis(self):
        """Test classification of crisis regime"""
        df = self.create_test_data(n_days=100)
        
        vix_data = self.create_vix_data(df.index, vix_level=40.0)  # Crisis VIX
        
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # All days should be crisis
        assert (regimes == RegimeType.CRISIS).sum() == 100
    
    def test_classify_regimes_ranging(self):
        """Test classification of ranging regime"""
        df = self.create_test_data(n_days=100)
        
        # Force ranging conditions
        df['close'] = df['ema_200'] * 1.01  # Price near EMA
        df['adx_14'] = 15.0  # Weak trend
        
        vix_data = self.create_vix_data(df.index, vix_level=20.0)  # Moderate VIX
        
        regimes = self.analyzer.classify_regimes(df, vix_data)
        
        # Most days should be ranging
        assert (regimes == RegimeType.RANGING).sum() > 50
    
    def test_classify_regimes_without_vix(self):
        """Test classification using VIX proxy when VIX data not provided"""
        df = self.create_test_data(n_days=100)
        
        # Classify without VIX data
        regimes = self.analyzer.classify_regimes(df, vix_data=None)
        
        # Should still produce valid regimes
        assert len(regimes) == 100
        assert all(r in [RegimeType.TRENDING_BULL, RegimeType.TRENDING_BEAR,
                        RegimeType.VOLATILE, RegimeType.CRISIS, RegimeType.RANGING]
                  for r in regimes.unique())
    
    def test_classify_regimes_missing_columns(self):
        """Test that missing required columns raises ValueError"""
        df = pd.DataFrame({
            'close': [100, 101, 102],
            'ema_200': [99, 100, 101]
            # Missing adx_14
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            self.analyzer.classify_regimes(df)
    
    def test_stratify_results_basic(self):
        """Test basic stratification of trades by regime"""
        # Create regimes
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        regimes = pd.Series([RegimeType.TRENDING_BULL] * 50 + [RegimeType.RANGING] * 50,
                           index=dates)
        
        # Create trades
        trades = [
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': 2.5},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': 3.0},
            {'entry_date': '2020-02-25', 'exit_date': '2020-03-01', 'pnl_pct': -1.0},
            {'entry_date': '2020-03-10', 'exit_date': '2020-03-15', 'pnl_pct': -0.5},
        ]
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Verify result structure
        assert isinstance(result, RegimeAnalysisResult)
        assert len(result.regime_returns) == 5
        assert len(result.regime_trade_counts) == 5
        assert len(result.regime_win_rates) == 5
        assert len(result.regime_sharpe_ratios) == 5
        assert len(result.recommendations) == 5
        assert result.overall_recommendation != ""
    
    def test_stratify_results_empty_trades(self):
        """Test stratification with no trades"""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        regimes = pd.Series([RegimeType.TRENDING_BULL] * 100, index=dates)
        
        result = self.analyzer.stratify_results([], regimes)
        
        assert result.overall_recommendation == "No trades to analyze"
        assert len(result.recommendations) == 0
    
    def test_stratify_results_performance_metrics(self):
        """Test that performance metrics are calculated correctly"""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        regimes = pd.Series([RegimeType.TRENDING_BULL] * 100, index=dates)
        
        # Create trades with known returns
        trades = [
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': 2.0},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': 3.0},
            {'entry_date': '2020-01-30', 'exit_date': '2020-02-05', 'pnl_pct': -1.0},
        ]
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Verify metrics for trending_bull regime
        assert result.regime_trade_counts[RegimeType.TRENDING_BULL] == 3
        assert result.regime_returns[RegimeType.TRENDING_BULL] == 4.0  # 2 + 3 - 1
        assert result.regime_win_rates[RegimeType.TRENDING_BULL] == pytest.approx(66.67, rel=0.1)  # 2 wins out of 3
    
    def test_stratify_results_recommendations_good_performance(self):
        """Test recommendations for good performance regime"""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        regimes = pd.Series([RegimeType.TRENDING_BULL] * 100, index=dates)
        
        # Create trades with good performance
        trades = [
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': 2.0},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': 3.0},
            {'entry_date': '2020-01-30', 'exit_date': '2020-02-05', 'pnl_pct': 2.5},
            {'entry_date': '2020-02-10', 'exit_date': '2020-02-15', 'pnl_pct': 1.5},
        ]
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Find trending_bull recommendation
        bull_rec = next(r for r in result.recommendations if r.regime == RegimeType.TRENDING_BULL)
        assert bull_rec.performance == "good"
        assert "performs well" in bull_rec.recommendation.lower()
    
    def test_stratify_results_recommendations_poor_performance(self):
        """Test recommendations for poor performance regime"""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        regimes = pd.Series([RegimeType.RANGING] * 100, index=dates)
        
        # Create trades with poor performance
        trades = [
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': -2.0},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': -1.5},
            {'entry_date': '2020-01-30', 'exit_date': '2020-02-05', 'pnl_pct': -1.0},
        ]
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Find ranging recommendation
        ranging_rec = next(r for r in result.recommendations if r.regime == RegimeType.RANGING)
        assert ranging_rec.performance == "poor"
        assert "ADX > 25" in ranging_rec.recommendation  # Should recommend ADX filter
    
    def test_stratify_results_overall_recommendation_robust(self):
        """Test overall recommendation for robust strategy"""
        dates = pd.date_range(start='2020-01-01', periods=500, freq='D')
        regimes = pd.Series(
            [RegimeType.TRENDING_BULL] * 100 +
            [RegimeType.TRENDING_BEAR] * 100 +
            [RegimeType.VOLATILE] * 100 +
            [RegimeType.CRISIS] * 100 +
            [RegimeType.RANGING] * 100,
            index=dates
        )
        
        # Create profitable trades in all regimes
        trades = []
        for i, date in enumerate(dates[::10]):  # Every 10th day
            trades.append({
                'entry_date': date.strftime('%Y-%m-%d'),
                'exit_date': (date + timedelta(days=5)).strftime('%Y-%m-%d'),
                'pnl_pct': 2.0
            })
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Should recommend all-weather deployment
        assert "robust" in result.overall_recommendation.lower() or "all-weather" in result.overall_recommendation.lower()
    
    def test_stratify_results_overall_recommendation_poor(self):
        """Test overall recommendation for poor strategy"""
        dates = pd.date_range(start='2020-01-01', periods=500, freq='D')
        regimes = pd.Series(
            [RegimeType.TRENDING_BULL] * 100 +
            [RegimeType.TRENDING_BEAR] * 100 +
            [RegimeType.VOLATILE] * 100 +
            [RegimeType.CRISIS] * 100 +
            [RegimeType.RANGING] * 100,
            index=dates
        )
        
        # Create losing trades in all regimes
        trades = []
        for i, date in enumerate(dates[::10]):  # Every 10th day
            trades.append({
                'entry_date': date.strftime('%Y-%m-%d'),
                'exit_date': (date + timedelta(days=5)).strftime('%Y-%m-%d'),
                'pnl_pct': -2.0
            })
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Should recommend redesign
        assert "redesign" in result.overall_recommendation.lower() or "struggles" in result.overall_recommendation.lower()
    
    def test_stratify_results_regime_specific_recommendations(self):
        """Test that regime-specific recommendations are generated"""
        dates = pd.date_range(start='2020-01-01', periods=200, freq='D')
        regimes = pd.Series(
            [RegimeType.VOLATILE] * 100 + [RegimeType.CRISIS] * 100,
            index=dates
        )
        
        # Poor performance in volatile and crisis
        trades = [
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': -3.0},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': -2.5},
            {'entry_date': '2020-04-10', 'exit_date': '2020-04-15', 'pnl_pct': -5.0},
            {'entry_date': '2020-04-20', 'exit_date': '2020-04-25', 'pnl_pct': -4.0},
        ]
        
        result = self.analyzer.stratify_results(trades, regimes)
        
        # Check volatile recommendation
        volatile_rec = next(r for r in result.recommendations if r.regime == RegimeType.VOLATILE)
        assert "VIX > 25" in volatile_rec.recommendation
        
        # Check crisis recommendation
        crisis_rec = next(r for r in result.recommendations if r.regime == RegimeType.CRISIS)
        assert "VIX > 35" in crisis_rec.recommendation or "circuit breaker" in crisis_rec.recommendation.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
