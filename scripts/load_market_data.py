"""
Load historical OHLCV data from yfinance into Supabase.
Cost: $0 — yfinance is free with no API key needed.

Usage:
    python scripts/load_market_data.py
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.config.settings import settings


# === CONFIGURE THESE ===

INSTRUMENTS = {
    # Indian Equities (NSE)
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "SBIN": "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "ITC": "ITC.NS",
    "KOTAKBANK": "KOTAKBANK.NS",
    "LT": "LT.NS",

    # Indices
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",

    # Crypto
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
}

DAYS = 100  # Fetch 100 days (need >=30 for training, 90 recommended)


def load_data():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(db_url)

    # Ensure table exists
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS market_data (
                id BIGSERIAL PRIMARY KEY,
                instrument VARCHAR(50) NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                open DOUBLE PRECISION NOT NULL,
                high DOUBLE PRECISION NOT NULL,
                low DOUBLE PRECISION NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                volume DOUBLE PRECISION NOT NULL,
                timeframe VARCHAR(10) DEFAULT '1D',
                source VARCHAR(20) DEFAULT 'yfinance',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(instrument, timestamp, timeframe)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_market_data_instrument_time 
            ON market_data(instrument, timestamp DESC)
        """))
        conn.commit()
    print("Table market_data ready\n")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=DAYS + 10)

    total_inserted = 0

    for signalixai_symbol, yf_ticker in INSTRUMENTS.items():
        print(f"Fetching {signalixai_symbol} ({yf_ticker})...", end=" ")

        try:
            ticker = yf.Ticker(yf_ticker)
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
            )

            if df.empty:
                print("WARNING: no data returned")
                continue

            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].copy()
            df = df.dropna()
            df = df[df["volume"] > 0]

            inserted = 0
            with engine.connect() as conn:
                for timestamp, row in df.iterrows():
                    try:
                        conn.execute(
                            text("""
                                INSERT INTO market_data 
                                    (instrument, timestamp, open, high, low, close, volume, timeframe, source)
                                VALUES 
                                    (:instrument, :timestamp, :open, :high, :low, :close, :volume, '1D', 'yfinance')
                                ON CONFLICT (instrument, timestamp, timeframe) DO NOTHING
                            """),
                            {
                                "instrument": signalixai_symbol,
                                "timestamp": timestamp.to_pydatetime(),
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": float(row["volume"]),
                            },
                        )
                        inserted += 1
                    except Exception:
                        pass
                conn.commit()

            print(f"{len(df)} bars fetched, {inserted} inserted")
            total_inserted += inserted

        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDONE: {total_inserted} total rows for {len(INSTRUMENTS)} instruments")


if __name__ == "__main__":
    load_data()
