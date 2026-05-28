"""
Market regime analyzer for backtesting.

Implements Paul Tudor Jones' macro awareness principle: understand how strategies
perform in different market conditions.

Requirements: 8.1–8.4
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from services.backtesting.models import BacktestResult


class RegimeType:
    """Market regime types"""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    VOLATILE = "volatile"
    CRISIS = "crisis"
    RANGING = "ranging"


class RegimeRecommendation(BaseModel):
    """Recommendation for a specific regime"""
    regime: str
    performance: str = Field(..., description="good/poor/neutral")
    recommendation: str = Field(..., description="Human-readable recommendation")


class RegimeAnalysisResult(BaseModel):
    """Results from regime analysis"""
    regime_returns: Dict[str, float] = Field(..., description="Returns by regime type")
    regime_trade_counts: Dict[str, int] = Field(..., description="Number of trades per regime")
    regime_win_rates: Dict[str, float] = Field(..., description="Win rate by regime (%)")
    regime_sharpe_ratios: Dict[str, float] = Field(..., description="Sharpe ratio by regime")
    recommendations: List[RegimeRecommendation] = Field(..., description="Recommendations for each regime")
    overall_recommendation: str = Field(..., description="Overall strategy recommendation")


class RegimeAnalyzer:
    """
    Market regime analyzer for strategy performance stratification.
    
    Classifies market conditions into 5 regimes and analyzes strategy performance
    in each regime to provide actionable recommendations.
    """
    
    def classify_regimes(
        self,
        data: pd.DataFrame,
        vix_data: Optional[pd.DataFrame] = None
    ) -> pd.Series:
        """
        Classify each day into one of five market regimes.
        
        Classification rules:
        - trending_bull: close > ema_200 AND adx_14 > 25 AND vix < 18
        - trending_bear: close < ema_200 AND adx_14 > 25 AND vix < 25
        - volatile: vix > 25 AND vix < 35
        - crisis: vix > 35
        - ranging: all other cases
        
        Args:
            data: DataFrame with OHLCV and indicators (must have: close, ema_200, adx_14)
            vix_data: Optional DataFrame with VIX data (must have: close column)
                     If None, uses a proxy based on ATR/price volatility
            
        Returns:
            pd.Series with regime classification for each date
            
        Raises:
            ValueError: If required columns are missing
        """
        # Validate required columns
        required_cols = ['close', 'ema_200', 'adx_14']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Create a copy to avoid modifying original
        df = data.copy()
        
        # If VIX data not provided, create a proxy using ATR-based volatility
        if vix_data is None or vix_data.empty:
            # Use ATR/price as volatility proxy, scaled to VIX-like range
            if 'atr_14' in df.columns:
                df['vix_proxy'] = (df['atr_14'] / df['close']) * 100 * 2.5
            else:
                # Fallback: use rolling std of returns
                returns = df['close'].pct_change()
                df['vix_proxy'] = returns.rolling(20).std() * np.sqrt(252) * 100
            vix_col = 'vix_proxy'
        else:
            # Merge VIX data
            vix_data = vix_data.copy()
            vix_data.columns = ['vix']
            df = df.join(vix_data, how='left')
            df['vix'] = df['vix'].ffill()  # Forward fill missing VIX
            vix_col = 'vix'
        
        # Initialize regime series
        regimes = pd.Series(index=df.index, dtype=str)
        
        # Apply classification rules in priority order
        # 1. Crisis (highest priority)
        crisis_mask = df[vix_col] > 35
        regimes[crisis_mask] = RegimeType.CRISIS
        
        # 2. Volatile
        volatile_mask = (df[vix_col] > 25) & (df[vix_col] <= 35)
        regimes[volatile_mask] = RegimeType.VOLATILE
        
        # 3. Trending Bull
        trending_bull_mask = (
            (df['close'] > df['ema_200']) &
            (df['adx_14'] > 25) &
            (df[vix_col] < 18)
        )
        regimes[trending_bull_mask] = RegimeType.TRENDING_BULL
        
        # 4. Trending Bear
        trending_bear_mask = (
            (df['close'] < df['ema_200']) &
            (df['adx_14'] > 25) &
            (df[vix_col] < 25)
        )
        regimes[trending_bear_mask] = RegimeType.TRENDING_BEAR
        
        # 5. Ranging (default for everything else)
        regimes[regimes.isna()] = RegimeType.RANGING
        
        return regimes
    
    def stratify_results(
        self,
        trades: List[dict],
        regimes: pd.Series,
        initial_capital: float = 100000.0
    ) -> RegimeAnalysisResult:
        """
        Stratify backtest results by market regime.
        
        Args:
            trades: List of trade dicts with entry_date, exit_date, pnl_pct
            regimes: pd.Series with regime classification by date
            initial_capital: Initial capital for return calculations
            
        Returns:
            RegimeAnalysisResult with performance metrics by regime
        """
        if not trades:
            # Return empty result if no trades
            return RegimeAnalysisResult(
                regime_returns={},
                regime_trade_counts={},
                regime_win_rates={},
                regime_sharpe_ratios={},
                recommendations=[],
                overall_recommendation="No trades to analyze"
            )
        
        # Group trades by regime
        regime_trades = {
            RegimeType.TRENDING_BULL: [],
            RegimeType.TRENDING_BEAR: [],
            RegimeType.VOLATILE: [],
            RegimeType.CRISIS: [],
            RegimeType.RANGING: []
        }
        
        for trade in trades:
            # Determine regime at entry date
            entry_date = pd.to_datetime(trade['entry_date'])
            if entry_date in regimes.index:
                regime = regimes[entry_date]
                if regime in regime_trades:
                    regime_trades[regime].append(trade)
        
        # Calculate metrics for each regime
        regime_returns = {}
        regime_trade_counts = {}
        regime_win_rates = {}
        regime_sharpe_ratios = {}
        
        for regime, regime_trade_list in regime_trades.items():
            if not regime_trade_list:
                regime_returns[regime] = 0.0
                regime_trade_counts[regime] = 0
                regime_win_rates[regime] = 0.0
                regime_sharpe_ratios[regime] = 0.0
                continue
            
            # Extract returns
            returns = [t['pnl_pct'] for t in regime_trade_list]
            
            # Calculate metrics
            regime_trade_counts[regime] = len(returns)
            regime_returns[regime] = sum(returns)
            
            # Win rate
            wins = sum(1 for r in returns if r > 0)
            regime_win_rates[regime] = (wins / len(returns)) * 100 if returns else 0.0
            
            # Sharpe ratio (simplified: mean / std)
            if len(returns) > 1:
                mean_return = np.mean(returns)
                std_return = np.std(returns, ddof=1)
                regime_sharpe_ratios[regime] = (mean_return / std_return) if std_return > 0 else 0.0
            else:
                regime_sharpe_ratios[regime] = 0.0
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            regime_returns,
            regime_trade_counts,
            regime_win_rates,
            regime_sharpe_ratios
        )
        
        # Generate overall recommendation
        overall_recommendation = self._generate_overall_recommendation(
            regime_returns,
            regime_trade_counts
        )
        
        return RegimeAnalysisResult(
            regime_returns=regime_returns,
            regime_trade_counts=regime_trade_counts,
            regime_win_rates=regime_win_rates,
            regime_sharpe_ratios=regime_sharpe_ratios,
            recommendations=recommendations,
            overall_recommendation=overall_recommendation
        )
    
    def _generate_recommendations(
        self,
        regime_returns: Dict[str, float],
        regime_trade_counts: Dict[str, int],
        regime_win_rates: Dict[str, float],
        regime_sharpe_ratios: Dict[str, float]
    ) -> List[RegimeRecommendation]:
        """Generate recommendations for each regime"""
        recommendations = []
        
        for regime in [RegimeType.TRENDING_BULL, RegimeType.TRENDING_BEAR,
                      RegimeType.VOLATILE, RegimeType.CRISIS, RegimeType.RANGING]:
            
            if regime_trade_counts[regime] == 0:
                recommendations.append(RegimeRecommendation(
                    regime=regime,
                    performance="neutral",
                    recommendation=f"No trades in {regime} regime - insufficient data"
                ))
                continue
            
            total_return = regime_returns[regime]
            win_rate = regime_win_rates[regime]
            sharpe = regime_sharpe_ratios[regime]
            
            # Classify performance
            if total_return > 0 and win_rate > 50 and sharpe > 1.0:
                performance = "good"
                recommendation = f"Strategy performs well in {regime} conditions. Continue trading."
            elif total_return < 0 or win_rate < 40:
                performance = "poor"
                # Generate specific recommendation based on regime
                if regime == RegimeType.RANGING:
                    recommendation = f"Poor performance in {regime} markets. Activate regime filter: only deploy when ADX > 25."
                elif regime == RegimeType.VOLATILE:
                    recommendation = f"Losses in {regime} conditions. Consider halting trading when VIX > 25."
                elif regime == RegimeType.CRISIS:
                    recommendation = f"Significant losses during {regime}. Implement VIX > 35 circuit breaker."
                elif regime == RegimeType.TRENDING_BEAR:
                    recommendation = f"Underperforming in {regime}. Consider adding short-side strategies or sitting out bear markets."
                else:
                    recommendation = f"Underperforming in {regime}. Review entry criteria for this regime."
            else:
                performance = "neutral"
                recommendation = f"Mixed results in {regime} conditions. Monitor closely."
            
            recommendations.append(RegimeRecommendation(
                regime=regime,
                performance=performance,
                recommendation=recommendation
            ))
        
        return recommendations
    
    def _generate_overall_recommendation(
        self,
        regime_returns: Dict[str, float],
        regime_trade_counts: Dict[str, int]
    ) -> str:
        """Generate overall strategy recommendation"""
        # Count regimes with positive returns
        positive_regimes = sum(1 for r in regime_returns.values() if r > 0)
        total_regimes_with_trades = sum(1 for c in regime_trade_counts.values() if c > 0)
        
        if total_regimes_with_trades == 0:
            return "Insufficient data for regime analysis"
        
        positive_ratio = positive_regimes / total_regimes_with_trades
        
        if positive_ratio >= 0.8:
            return "Strategy is robust across most market regimes. Suitable for all-weather deployment."
        elif positive_ratio >= 0.6:
            return "Strategy performs well in most conditions. Consider regime filters for underperforming regimes."
        elif positive_ratio >= 0.4:
            return "Mixed regime performance. Implement regime-based filters to avoid poor-performing conditions."
        else:
            return "Strategy struggles in most regimes. Significant redesign recommended before live deployment."
