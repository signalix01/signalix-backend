"""
SuperTrend Indicator Implementation.

SuperTrend is an ATR-based trend-following indicator developed by Olivier Seban.
It provides dynamic support and resistance levels that adapt to market volatility.

Algorithm:
1. Calculate ATR (Average True Range)
2. Calculate basic upper and lower bands using HL average ± (multiplier × ATR)
3. Apply band smoothing logic to prevent whipsaws
4. Determine trend direction based on price position relative to bands

When price is above SuperTrend line: bullish trend (direction = +1)
When price is below SuperTrend line: bearish trend (direction = -1)

Requirements: 1.4 (SuperTrend in IndicatorType)
"""

import pandas as pd
import numpy as np
import talib
from typing import Tuple


def compute_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0
) -> Tuple[pd.Series, pd.Series]:
    """
    Compute SuperTrend indicator.

    Args:
        df: DataFrame with OHLCV data (must have 'high', 'low', 'close' columns)
        period: ATR period (default: 10)
        multiplier: ATR multiplier for band calculation (default: 3.0)

    Returns:
        Tuple of (supertrend_line, direction) as pandas Series
        - supertrend_line: The SuperTrend line values
        - direction: +1 for bullish, -1 for bearish

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 101, 103, 105],
        ...     'low': [98, 99, 98, 100, 102],
        ...     'close': [99, 101, 100, 102, 104]
        ... })
        >>> supertrend, direction = compute_supertrend(df, period=3, multiplier=2.0)
    """
    # Validate input
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame must contain '{col}' column")

    if len(df) < period:
        raise ValueError(f"DataFrame must have at least {period} rows for period={period}")

    # Calculate ATR using TA-Lib
    atr = talib.ATR(
        df['high'].values.astype(float),
        df['low'].values.astype(float),
        df['close'].values.astype(float),
        timeperiod=period
    )

    # Calculate HL average (typical price without volume)
    hl_avg = (df['high'] + df['low']) / 2

    # Calculate basic upper and lower bands
    basic_upper = hl_avg + (multiplier * atr)
    basic_lower = hl_avg - (multiplier * atr)

    # Initialize final bands (these will be smoothed)
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()

    # Initialize supertrend and direction series
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    # Set initial values
    supertrend.iloc[0] = basic_upper.iloc[0]
    direction.iloc[0] = -1  # Start with bearish

    # Iterate through data to compute SuperTrend
    for i in range(1, len(df)):
        # Final upper band calculation
        # If basic upper is less than previous final upper OR
        # previous close was above previous final upper,
        # then use basic upper, otherwise keep previous final upper
        if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]

        # Final lower band calculation
        # If basic lower is greater than previous final lower OR
        # previous close was below previous final lower,
        # then use basic lower, otherwise keep previous final lower
        if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]

        # Determine SuperTrend value and direction
        if supertrend.iloc[i-1] == final_upper.iloc[i-1]:
            # Previous trend was bearish (price below upper band)
            if df['close'].iloc[i] <= final_upper.iloc[i]:
                # Still bearish
                supertrend.iloc[i] = final_upper.iloc[i]
                direction.iloc[i] = -1
            else:
                # Trend reversal to bullish
                supertrend.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = 1
        else:
            # Previous trend was bullish (price above lower band)
            if df['close'].iloc[i] >= final_lower.iloc[i]:
                # Still bullish
                supertrend.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = 1
            else:
                # Trend reversal to bearish
                supertrend.iloc[i] = final_upper.iloc[i]
                direction.iloc[i] = -1

    return supertrend, direction
