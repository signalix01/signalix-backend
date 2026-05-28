"""
BacktestDataPipeline: Historical data fetching, caching, and indicator computation.

Supports all markets: NSE/BSE (Angel One), Crypto (Binance), Forex (OANDA),
US Equities (Polygon.io), MCX Commodities (Angel One).

Requirements: 4.2, 4.3, 4.4
"""

import pandas as pd
import numpy as np
try:
    import talib
    HAS_TALIB = True
except ImportError:
    talib = None  # type: ignore
    HAS_TALIB = False
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    """Asset class enumeration"""
    NSE_EQUITY = "NSE_EQUITY"
    NSE_FO = "NSE_FO"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    COMMODITY = "COMMODITY"
    US_EQUITY = "US_EQUITY"


class BacktestDataPipeline:
    """
    Fetches, cleans, and validates historical OHLCV data for backtesting.
    Supports all markets: NSE/BSE (Angel One), Crypto (Binance), Forex (OANDA),
    US Equities (Polygon.io), MCX Commodities (Angel One).
    """

    MARKET_DATA_SOURCES = {
        "NSE_EQUITY": {"primary": "angel_one", "fallback": "yfinance", "max_history_years": 10},
        "NSE_FO": {"primary": "angel_one", "options_history": True, "max_history_years": 5},
        "CRYPTO": {"primary": "binance", "fallback": "ccxt_multiple", "max_history_years": 8},
        "FOREX": {"primary": "oanda", "fallback": "alpha_vantage", "max_history_years": 10},
        "COMMODITY": {"primary": "angel_one_mcx", "fallback": "quandl", "max_history_years": 7},
        "US_EQUITY": {"primary": "polygon_io", "fallback": "alpaca", "max_history_years": 10},
    }

    def __init__(self, db_connection=None, redis_client=None):
        """
        Initialize the data pipeline.

        Args:
            db_connection: Database connection for TimescaleDB caching
            redis_client: Redis client for temporary caching
        """
        self.db = db_connection
        self.redis = redis_client

    async def get_backtest_data(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str,
        asset_class: str
    ) -> pd.DataFrame:
        """
        Returns clean OHLCV DataFrame with computed TA-Lib indicators.
        Data is cached in TimescaleDB. Only calls broker API for missing ranges.

        Args:
            instrument: Symbol/ticker (e.g., "BANKNIFTY", "BTCUSDT")
            start: Start date in ISO format (YYYY-MM-DD)
            end: End date in ISO format (YYYY-MM-DD)
            timeframe: Candle timeframe (e.g., "1m", "5m", "1h", "1D")
            asset_class: Asset class (NSE_EQUITY, CRYPTO, etc.)

        Returns:
            DataFrame with OHLCV data and all computed indicators
        """
        logger.info(f"Fetching backtest data for {instrument} from {start} to {end}, timeframe={timeframe}")

        # Check TimescaleDB cache first
        cached = await self.fetch_from_timescale(instrument, start, end, timeframe)

        if cached is not None and len(cached) > 0:
            missing_ranges = self.find_missing_ranges(cached, start, end, timeframe)
            if not missing_ranges:
                logger.info(f"Cache hit: {len(cached)} bars for {instrument}")
                return self.compute_indicators(cached)
            logger.info(f"Partial cache hit: {len(missing_ranges)} missing ranges")
        else:
            logger.info(f"Cache miss for {instrument}")
            missing_ranges = [(start, end)]

        # Fetch missing data from primary source
        source_config = self.MARKET_DATA_SOURCES.get(asset_class.upper())
        if not source_config:
            raise ValueError(f"Unsupported asset class: {asset_class}")

        all_data = cached if cached is not None else pd.DataFrame()

        for missing_start, missing_end in missing_ranges:
            raw_data = await self.fetch_from_source(
                instrument, missing_start, missing_end, timeframe, source_config, asset_class
            )
            if raw_data is not None and len(raw_data) > 0:
                all_data = pd.concat([all_data, raw_data]).drop_duplicates().sort_index()

        if all_data.empty:
            raise ValueError(f"No data available for {instrument} in the requested period")

        # Validate: check for splits, dividends, data gaps
        validated_data = self.validate_and_adjust(all_data, instrument, asset_class)

        # Store in TimescaleDB for future use
        await self.store_in_timescale(validated_data, instrument, timeframe)

        return self.compute_indicators(validated_data)

    async def fetch_from_timescale(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch cached OHLCV data from TimescaleDB.

        Args:
            instrument: Symbol/ticker
            start: Start date (ISO format)
            end: End date (ISO format)
            timeframe: Candle timeframe

        Returns:
            DataFrame with cached data or None if not found
        """
        if not self.db:
            logger.warning("No database connection available for caching")
            return None

        try:
            # Query TimescaleDB hypertable
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM ohlcv_data
                WHERE instrument = $1
                  AND timeframe = $2
                  AND timestamp >= $3::timestamp
                  AND timestamp <= $4::timestamp
                ORDER BY timestamp ASC
            """
            rows = await self.db.fetch_all(query, instrument, timeframe, start, end)

            if not rows:
                return None

            df = pd.DataFrame(rows)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error fetching from TimescaleDB: {e}")
            return None

    def find_missing_ranges(
        self,
        cached_data: pd.DataFrame,
        start: str,
        end: str,
        timeframe: str
    ) -> List[Tuple[str, str]]:
        """
        Identify gaps in cached data.

        Args:
            cached_data: DataFrame with cached OHLCV data
            start: Requested start date
            end: Requested end date
            timeframe: Candle timeframe

        Returns:
            List of (start, end) tuples representing missing date ranges
        """
        if cached_data.empty:
            return [(start, end)]

        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)

        # Get the actual range in cached data
        cached_start = cached_data.index.min()
        cached_end = cached_data.index.max()

        missing_ranges = []

        # Check if we need data before cached range
        if start_dt < cached_start:
            missing_ranges.append((start, cached_start.strftime('%Y-%m-%d')))

        # Check if we need data after cached range
        if end_dt > cached_end:
            missing_ranges.append((cached_end.strftime('%Y-%m-%d'), end))

        # TODO: Check for gaps within the cached data
        # This would require analyzing the expected frequency based on timeframe

        return missing_ranges

    async def fetch_from_source(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str,
        source_config: Dict[str, Any],
        asset_class: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch data from the appropriate source based on asset class.

        Args:
            instrument: Symbol/ticker
            start: Start date
            end: End date
            timeframe: Candle timeframe
            source_config: Source configuration dict
            asset_class: Asset class

        Returns:
            DataFrame with OHLCV data
        """
        primary_source = source_config.get("primary")

        try:
            # Dispatch to appropriate fetcher
            if primary_source == "angel_one":
                return await self.fetch_angel_one(instrument, start, end, timeframe)
            elif primary_source == "binance":
                return await self.fetch_binance(instrument, start, end, timeframe)
            elif primary_source == "oanda":
                return await self.fetch_oanda(instrument, start, end, timeframe)
            elif primary_source == "polygon_io":
                return await self.fetch_polygon(instrument, start, end, timeframe)
            else:
                logger.warning(f"Unknown primary source: {primary_source}, trying fallback")
                return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)

        except Exception as e:
            logger.error(f"Error fetching from {primary_source}: {e}")
            # Try fallback
            fallback = source_config.get("fallback")
            if fallback:
                logger.info(f"Trying fallback source: {fallback}")
                return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)
            raise

    async def fetch_angel_one(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Fetch data from Angel One SmartAPI.

        Args:
            instrument: NSE symbol
            start: Start date
            end: End date
            timeframe: Candle timeframe

        Returns:
            DataFrame with OHLCV data
        """
        # TODO: Implement Angel One SmartAPI integration
        # This requires Angel One API credentials and the SmartAPI Python client
        logger.warning("Angel One fetcher not yet implemented, using fallback")
        return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)

    async def fetch_binance(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Fetch data from Binance API.

        Args:
            instrument: Binance symbol (e.g., "BTCUSDT")
            start: Start date
            end: End date
            timeframe: Candle timeframe

        Returns:
            DataFrame with OHLCV data
        """
        # TODO: Implement Binance API integration
        # This requires the python-binance library
        logger.warning("Binance fetcher not yet implemented, using fallback")
        return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)

    async def fetch_oanda(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Fetch data from OANDA v20 API.

        Args:
            instrument: OANDA instrument (e.g., "EUR_USD")
            start: Start date
            end: End date
            timeframe: Candle timeframe

        Returns:
            DataFrame with OHLCV data
        """
        # TODO: Implement OANDA v20 API integration
        logger.warning("OANDA fetcher not yet implemented, using fallback")
        return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)

    async def fetch_polygon(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Fetch data from Polygon.io API.

        Args:
            instrument: US equity ticker
            start: Start date
            end: End date
            timeframe: Candle timeframe

        Returns:
            DataFrame with OHLCV data
        """
        # TODO: Implement Polygon.io API integration
        logger.warning("Polygon.io fetcher not yet implemented, using fallback")
        return await self.fetch_yfinance_fallback(instrument, start, end, timeframe)

    async def fetch_yfinance_fallback(
        self,
        instrument: str,
        start: str,
        end: str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Fallback data fetcher using yfinance library.

        Args:
            instrument: Symbol/ticker
            start: Start date
            end: End date
            timeframe: Candle timeframe

        Returns:
            DataFrame with OHLCV data
        """
        try:
            import yfinance as yf

            # Map timeframe to yfinance interval
            interval_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "1h", "1D": "1d", "1W": "1wk", "1M": "1mo"
            }
            interval = interval_map.get(timeframe, "1d")

            ticker = yf.Ticker(instrument)
            df = ticker.history(start=start, end=end, interval=interval)

            if df.empty:
                raise ValueError(f"No data returned from yfinance for {instrument}")

            # Standardize column names
            df.columns = [col.lower() for col in df.columns]
            df = df[['open', 'high', 'low', 'close', 'volume']]

            logger.info(f"Fetched {len(df)} bars from yfinance for {instrument}")
            return df

        except Exception as e:
            logger.error(f"Error fetching from yfinance: {e}")
            raise

    def validate_and_adjust(
        self,
        df: pd.DataFrame,
        instrument: str,
        asset_class: str
    ) -> pd.DataFrame:
        """
        Validate and adjust data for splits, dividends, and gaps.

        Args:
            df: Raw OHLCV DataFrame
            instrument: Symbol/ticker
            asset_class: Asset class

        Returns:
            Validated and adjusted DataFrame
        """
        logger.info(f"Validating data for {instrument}")

        # Check for missing values
        if df.isnull().any().any():
            logger.warning(f"Found null values in {instrument} data, forward filling")
            df = df.fillna(method='ffill')

        # Check for zero or negative prices
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if (df[col] <= 0).any():
                logger.warning(f"Found zero/negative {col} prices in {instrument}, removing")
                df = df[df[col] > 0]

        # Check for data gaps (more than 3 consecutive missing days for daily data)
        # TODO: Implement gap detection based on timeframe

        # Check for potential stock splits (price jumps > 50%)
        df['price_change'] = df['close'].pct_change()
        large_jumps = df[abs(df['price_change']) > 0.5]
        if len(large_jumps) > 0:
            logger.warning(f"Found {len(large_jumps)} potential splits/dividends in {instrument}")
            # TODO: Implement split adjustment logic

        df = df.drop('price_change', axis=1)

        # Ensure data is sorted by timestamp
        df = df.sort_index()

        logger.info(f"Validation complete: {len(df)} bars for {instrument}")
        return df

    async def store_in_timescale(
        self,
        df: pd.DataFrame,
        instrument: str,
        timeframe: str
    ) -> None:
        """
        Store OHLCV data in TimescaleDB for caching.

        Args:
            df: OHLCV DataFrame
            instrument: Symbol/ticker
            timeframe: Candle timeframe
        """
        if not self.db:
            logger.warning("No database connection available for caching")
            return

        try:
            # Prepare data for insertion
            records = []
            for timestamp, row in df.iterrows():
                records.append({
                    'instrument': instrument,
                    'timeframe': timeframe,
                    'timestamp': timestamp,
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume'])
                })

            # Batch insert with ON CONFLICT DO NOTHING to avoid duplicates
            query = """
                INSERT INTO ohlcv_data (instrument, timeframe, timestamp, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (instrument, timeframe, timestamp) DO NOTHING
            """

            for record in records:
                await self.db.execute(
                    query,
                    record['instrument'],
                    record['timeframe'],
                    record['timestamp'],
                    record['open'],
                    record['high'],
                    record['low'],
                    record['close'],
                    record['volume']
                )

            logger.info(f"Stored {len(records)} bars in TimescaleDB for {instrument}")

        except Exception as e:
            logger.error(f"Error storing in TimescaleDB: {e}")
            # Don't raise - caching failure shouldn't break the pipeline

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Pre-compute ALL indicators used by the strategy compiler.

        Computes:
        - RSI for periods: 5, 9, 14, 20, 21, 50, 200
        - EMA for periods: 5, 9, 14, 20, 21, 50, 200
        - SMA for periods: 5, 9, 14, 20, 21, 50, 200
        - MACD (12, 26, 9)
        - Bollinger Bands (20, 2.0)
        - ATR (14)
        - ADX (14)
        - Stochastic Oscillator
        - CCI (14)
        - MFI (14)
        - OBV
        - VWAP
        - SuperTrend (10, 3.0)
        - Rolling max/min for periods: 5, 10, 20, 52

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with all computed indicators
        """
        logger.info(f"Computing indicators for {len(df)} bars")

        # Make a copy to avoid modifying original
        df = df.copy()

        if not HAS_TALIB:
            logger.warning(
                "TA-Lib not installed — computing basic indicators with pandas only. "
                "Install TA-Lib for full indicator support."
            )
            return self._compute_indicators_pandas(df)

        # Convert to numpy arrays for TA-Lib
        closes = df['close'].values.astype(float)
        highs = df['high'].values.astype(float)
        lows = df['low'].values.astype(float)
        opens = df['open'].values.astype(float)
        volumes = df['volume'].values.astype(float)

        # RSI, EMA, SMA for multiple periods
        for period in [5, 9, 14, 20, 21, 50, 200]:
            try:
                df[f'rsi_{period}'] = talib.RSI(closes, timeperiod=period)
                df[f'ema_{period}'] = talib.EMA(closes, timeperiod=period)
                df[f'sma_{period}'] = talib.SMA(closes, timeperiod=period)
            except Exception as e:
                logger.warning(f"Error computing indicators for period {period}: {e}")

        # MACD
        try:
            macd, signal, hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
            df['macd'] = macd
            df['macd_signal'] = signal
            df['macd_hist'] = hist
        except Exception as e:
            logger.warning(f"Error computing MACD: {e}")

        # Bollinger Bands
        try:
            upper, mid, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
            df['bb_upper'] = upper
            df['bb_mid'] = mid
            df['bb_lower'] = lower
        except Exception as e:
            logger.warning(f"Error computing Bollinger Bands: {e}")

        # ATR
        try:
            df['atr_14'] = talib.ATR(highs, lows, closes, timeperiod=14)
        except Exception as e:
            logger.warning(f"Error computing ATR: {e}")

        # ADX
        try:
            df['adx_14'] = talib.ADX(highs, lows, closes, timeperiod=14)
        except Exception as e:
            logger.warning(f"Error computing ADX: {e}")

        # Stochastic Oscillator
        try:
            stoch_k, stoch_d = talib.STOCH(highs, lows, closes,
                                           fastk_period=14, slowk_period=3, slowd_period=3)
            df['stoch_k'] = stoch_k
            df['stoch_d'] = stoch_d
        except Exception as e:
            logger.warning(f"Error computing Stochastic: {e}")

        # CCI
        try:
            df['cci_14'] = talib.CCI(highs, lows, closes, timeperiod=14)
        except Exception as e:
            logger.warning(f"Error computing CCI: {e}")

        # MFI
        try:
            df['mfi_14'] = talib.MFI(highs, lows, closes, volumes, timeperiod=14)
        except Exception as e:
            logger.warning(f"Error computing MFI: {e}")

        # OBV
        try:
            df['obv'] = talib.OBV(closes, volumes)
        except Exception as e:
            logger.warning(f"Error computing OBV: {e}")

        # VWAP (cumulative)
        try:
            df['vwap'] = (closes * volumes).cumsum() / volumes.cumsum()
        except Exception as e:
            logger.warning(f"Error computing VWAP: {e}")

        # Rolling window features (highest high, lowest low)
        for n in [5, 10, 20, 52]:
            try:
                df[f'highest_high_{n}'] = df['high'].rolling(window=n).max()
                df[f'lowest_low_{n}'] = df['low'].rolling(window=n).min()
            except Exception as e:
                logger.warning(f"Error computing rolling features for period {n}: {e}")

        # Volume moving average
        try:
            df['volume_ma_20'] = talib.SMA(volumes, timeperiod=20)
        except Exception as e:
            logger.warning(f"Error computing volume MA: {e}")

        # SuperTrend calculation
        try:
            supertrend, direction = self.compute_supertrend(df, period=10, multiplier=3.0)
            df['supertrend'] = supertrend
            df['supertrend_direction'] = direction
        except Exception as e:
            logger.warning(f"Error computing SuperTrend: {e}")

        # Drop rows with NaN values (from indicator computation)
        initial_len = len(df)
        df = df.dropna()
        dropped = initial_len - len(df)
        if dropped > 0:
            logger.info(f"Dropped {dropped} rows with NaN values after indicator computation")

        logger.info(f"Indicator computation complete: {len(df)} bars with {len(df.columns)} columns")
        return df

    def compute_supertrend(
        self,
        df: pd.DataFrame,
        period: int = 10,
        multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Compute SuperTrend indicator.

        SuperTrend is an ATR-based trend-following indicator.
        - When price is above SuperTrend line: bullish (direction = +1)
        - When price is below SuperTrend line: bearish (direction = -1)

        Args:
            df: DataFrame with OHLCV data
            period: ATR period (default: 10)
            multiplier: ATR multiplier (default: 3.0)

        Returns:
            Tuple of (supertrend_line, direction) as pandas Series
        """
        # Calculate ATR
        atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=period)

        # Calculate basic upper and lower bands
        hl_avg = (df['high'] + df['low']) / 2
        basic_upper = hl_avg + (multiplier * atr)
        basic_lower = hl_avg - (multiplier * atr)

        # Initialize final bands
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()

        # Initialize supertrend and direction
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)

        # First value
        supertrend.iloc[0] = basic_upper.iloc[0]
        direction.iloc[0] = -1

        for i in range(1, len(df)):
            # Final upper band
            if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]

            # Final lower band
            if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i-1]

            # SuperTrend
            if supertrend.iloc[i-1] == final_upper.iloc[i-1]:
                if df['close'].iloc[i] <= final_upper.iloc[i]:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1
                else:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1
            else:
                if df['close'].iloc[i] >= final_lower.iloc[i]:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1
                else:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1

        return supertrend, direction

    def _compute_indicators_pandas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Pandas-only fallback when TA-Lib is not installed."""
        closes = df['close']
        highs = df['high']
        lows = df['low']
        volumes = df['volume']

        for period in [5, 9, 14, 20, 21, 50, 200]:
            # EMA & SMA
            df[f'ema_{period}'] = closes.ewm(span=period, adjust=False).mean()
            df[f'sma_{period}'] = closes.rolling(window=period).mean()
            # RSI
            delta = closes.diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
            rs = gain / loss.replace(0, np.nan)
            df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Bollinger Bands
        sma20 = closes.rolling(window=20).mean()
        std20 = closes.rolling(window=20).std()
        df['bb_upper'] = sma20 + 2 * std20
        df['bb_mid'] = sma20
        df['bb_lower'] = sma20 - 2 * std20

        # ATR
        tr = pd.concat([
            highs - lows,
            (highs - closes.shift()).abs(),
            (lows - closes.shift()).abs()
        ], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(window=14).mean()

        # VWAP
        df['vwap'] = (closes * volumes).cumsum() / volumes.cumsum()

        # Rolling features
        for n in [5, 10, 20, 52]:
            df[f'highest_high_{n}'] = highs.rolling(window=n).max()
            df[f'lowest_low_{n}'] = lows.rolling(window=n).min()

        df['volume_ma_20'] = volumes.rolling(window=20).mean()

        return df
