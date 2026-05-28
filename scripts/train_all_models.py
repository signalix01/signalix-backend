"""
Train Isolation Forest models for all instruments with data.
This is the manual equivalent of what Celery Beat does at 03:00 IST.

Usage:
    python scripts/train_all_models.py
"""

import time
import pandas as pd
from sqlalchemy import create_engine, text
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.config.settings import settings
from services.alerts.detectors.isolation_forest import IsolationForestDetector


def train_all():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(db_url)

    # Get all instruments with enough data
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT instrument, COUNT(*) as bar_count
            FROM market_data
            WHERE timeframe = '1D'
            GROUP BY instrument
            HAVING COUNT(*) >= 30
            ORDER BY instrument
        """))
        instruments = [(row[0], row[1]) for row in result.fetchall()]

    if not instruments:
        print("No instruments with enough data (need >= 30 bars)")
        print("Run scripts/load_market_data.py first!")
        return

    print(f"Training models for {len(instruments)} instruments\n")

    detector = IsolationForestDetector()
    successful = 0
    failed = 0
    start = time.time()

    for symbol, count in instruments:
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT timestamp, open, high, low, close, volume
                        FROM market_data
                        WHERE instrument = :instrument AND timeframe = '1D'
                        ORDER BY timestamp ASC
                    """),
                    {"instrument": symbol},
                )
                rows = result.fetchall()

            df = pd.DataFrame(
                rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            t0 = time.time()
            detector.train(df, instrument=symbol)
            elapsed = time.time() - t0

            print(f"  [OK] {symbol:15s} | {count:3d} bars | {elapsed:.2f}s")
            successful += 1

        except Exception as e:
            print(f"  [FAIL] {symbol:15s} | {e}")
            failed += 1

    total_time = time.time() - start
    print(f"\n{'='*50}")
    print(f"Results: {successful} successful, {failed} failed")
    print(f"Total time: {total_time:.1f}s")
    print(f"Models cached in Redis with 48h TTL")


if __name__ == "__main__":
    train_all()
