"""
Verification script for Task 18: Market Regime Analysis

This script demonstrates the regime analyzer working with 2 years of data
and verifies all 5 regime types are present.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from services.backtesting.regime_analyzer import RegimeAnalyzer, RegimeType


def create_two_year_dataset():
    """Create 2 years of synthetic OHLCV data with indicators"""
    # 2 years = 730 days
    n_days = 730
    dates = pd.date_range(start='2022-01-01', periods=n_days, freq='D')
    
    # Create synthetic price data with trend
    np.random.seed(42)
    trend = np.linspace(100, 150, n_days)  # Upward trend
    noise = np.random.randn(n_days) * 5
    close_prices = trend + noise
    
    df = pd.DataFrame({
        'close': close_prices,
        'high': close_prices * 1.02,
        'low': close_prices * 0.98,
        'open': close_prices * 0.99,
        'volume': np.random.randint(1000000, 5000000, n_days),
    }, index=dates)
    
    # Add indicators
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Vary ADX to create different regimes
    df['adx_14'] = np.random.uniform(15, 40, n_days)
    
    # Make some periods have strong trends
    df.loc[df.index[:200], 'adx_14'] = np.random.uniform(26, 40, 200)  # Strong trend
    df.loc[df.index[200:400], 'adx_14'] = np.random.uniform(15, 24, 200)  # Weak trend
    df.loc[df.index[400:600], 'adx_14'] = np.random.uniform(26, 35, 200)  # Strong trend
    
    df['atr_14'] = df['close'] * 0.02  # 2% ATR
    
    return df


def create_varied_vix_data(dates):
    """Create VIX data with all regime levels"""
    n_days = len(dates)
    vix_values = []
    
    # Cycle through different VIX levels to ensure all regimes appear
    for i in range(n_days):
        if i < 146:  # First 20%: low VIX (trending bull potential)
            vix_values.append(np.random.uniform(12, 17))
        elif i < 292:  # Next 20%: moderate VIX (trending bear potential)
            vix_values.append(np.random.uniform(18, 24))
        elif i < 438:  # Next 20%: high VIX (volatile)
            vix_values.append(np.random.uniform(26, 34))
        elif i < 584:  # Next 20%: crisis VIX
            vix_values.append(np.random.uniform(36, 50))
        else:  # Last 20%: back to low (ranging potential)
            vix_values.append(np.random.uniform(15, 22))
    
    return pd.DataFrame({'close': vix_values}, index=dates)


def main():
    """Run verification"""
    print("=" * 70)
    print("Task 18 Verification: Market Regime Analysis")
    print("=" * 70)
    print()
    
    # Create analyzer
    analyzer = RegimeAnalyzer()
    print("✓ RegimeAnalyzer initialized")
    
    # Create 2 years of data
    print("\n1. Creating 2 years of BANKNIFTY-like data...")
    data = create_two_year_dataset()
    print(f"   ✓ Created {len(data)} days of data ({data.index[0].date()} to {data.index[-1].date()})")
    print(f"   ✓ Data shape: {data.shape}")
    print(f"   ✓ Columns: {list(data.columns)}")
    
    # Create VIX data
    print("\n2. Creating VIX data with varied levels...")
    vix_data = create_varied_vix_data(data.index)
    print(f"   ✓ VIX range: {vix_data['close'].min():.2f} to {vix_data['close'].max():.2f}")
    
    # Classify regimes
    print("\n3. Classifying market regimes...")
    regimes = analyzer.classify_regimes(data, vix_data)
    print(f"   ✓ Classified {len(regimes)} days")
    
    # Count regime types
    print("\n4. Regime Distribution:")
    regime_counts = regimes.value_counts()
    total_days = len(regimes)
    
    all_regimes = [
        RegimeType.TRENDING_BULL,
        RegimeType.TRENDING_BEAR,
        RegimeType.VOLATILE,
        RegimeType.CRISIS,
        RegimeType.RANGING
    ]
    
    for regime in all_regimes:
        count = regime_counts.get(regime, 0)
        pct = (count / total_days) * 100
        status = "✓" if count > 0 else "✗"
        print(f"   {status} {regime:20s}: {count:4d} days ({pct:5.1f}%)")
    
    # Verify all 5 regimes present
    unique_regimes = set(regimes.unique())
    all_present = all(regime in unique_regimes for regime in all_regimes)
    
    print("\n5. Verification Result:")
    if all_present:
        print("   ✓ SUCCESS: All 5 regime types are present in the 2-year dataset")
    else:
        missing = [r for r in all_regimes if r not in unique_regimes]
        print(f"   ✗ FAILURE: Missing regimes: {missing}")
        return False
    
    # Create sample trades for stratification test
    print("\n6. Testing stratification with sample trades...")
    trades = []
    for i, date in enumerate(data.index[::30]):  # Every 30 days
        trades.append({
            'entry_date': date.strftime('%Y-%m-%d'),
            'exit_date': (date + timedelta(days=5)).strftime('%Y-%m-%d'),
            'pnl_pct': np.random.uniform(-2, 3)  # Random P&L
        })
    
    print(f"   ✓ Created {len(trades)} sample trades")
    
    # Stratify results
    regime_results = analyzer.stratify_results(trades, regimes, initial_capital=100000.0)
    
    print("\n7. Regime Performance Summary:")
    for regime in all_regimes:
        trade_count = regime_results.regime_trade_counts.get(regime, 0)
        if trade_count > 0:
            returns = regime_results.regime_returns[regime]
            win_rate = regime_results.regime_win_rates[regime]
            sharpe = regime_results.regime_sharpe_ratios[regime]
            print(f"   {regime:20s}: {trade_count:2d} trades, {returns:+6.2f}% return, "
                  f"{win_rate:5.1f}% win rate, Sharpe: {sharpe:5.2f}")
    
    print(f"\n8. Overall Recommendation:")
    print(f"   {regime_results.overall_recommendation}")
    
    print("\n9. Regime-Specific Recommendations:")
    for rec in regime_results.recommendations:
        if rec.performance != "neutral":
            print(f"   • {rec.regime} ({rec.performance}): {rec.recommendation}")
    
    print("\n" + "=" * 70)
    print("✓ Task 18 Verification COMPLETE")
    print("=" * 70)
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
