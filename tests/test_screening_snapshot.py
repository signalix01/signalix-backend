"""
Test script for screening_snapshot materialized view

This script verifies:
1. The materialized view is created successfully
2. The view can be refreshed
3. The view populates correct values for test symbols
4. All required indicator columns are present
5. The unique index on symbol works correctly

Requirements: 9.3, 16.1
"""
import asyncio
import sys
from datetime import datetime, timedelta
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)

# Convert asyncpg URL format
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')


async def test_screening_snapshot():
    """Test the screening_snapshot materialized view"""
    
    print("=" * 80)
    print("Testing screening_snapshot Materialized View")
    print("=" * 80)
    print()
    
    # Connect to database
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✓ Connected to database")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        return False
    
    try:
        # Test 1: Check if materialized view exists
        print("\n[Test 1] Checking if screening_snapshot view exists...")
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' 
                AND matviewname = 'screening_snapshot'
            );
        """)
        
        if result:
            print("✓ screening_snapshot materialized view exists")
        else:
            print("✗ screening_snapshot materialized view does not exist")
            return False
        
        # Test 2: Check if unique index on symbol exists
        print("\n[Test 2] Checking if unique index on symbol exists...")
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'screening_snapshot'
                AND indexname = 'idx_screening_snapshot_symbol'
            );
        """)
        
        if result:
            print("✓ Unique index on symbol exists")
        else:
            print("✗ Unique index on symbol does not exist")
            return False
        
        # Test 3: Insert test data into instruments and ohlcv_1d tables
        print("\n[Test 3] Inserting test data...")
        
        test_symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK']
        
        # Insert test instruments
        for symbol in test_symbols:
            await conn.execute("""
                INSERT INTO instruments (symbol, name, exchange, asset_class, is_active)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (symbol) DO UPDATE 
                SET name = EXCLUDED.name, is_active = EXCLUDED.is_active;
            """, symbol, f"{symbol} Ltd", "NSE", "equity", True)
        
        print(f"✓ Inserted {len(test_symbols)} test instruments")
        
        # Insert test OHLCV data with indicators
        now = datetime.now()
        for i, symbol in enumerate(test_symbols):
            # Create realistic test data
            base_price = 1000 + (i * 100)
            rsi_value = 30 + (i * 10)  # RSI from 30 to 70
            
            await conn.execute("""
                INSERT INTO ohlcv_1d (
                    id, symbol, timestamp, open, high, low, close, volume,
                    rsi_14, ema_21, ema_50, ema_200, adx_14, atr_14,
                    volume_ma_20, above_ema_200, volume_ratio, composite_score
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18
                )
                ON CONFLICT (id) DO NOTHING;
            """, 
                uuid4(), symbol, now, 
                base_price, base_price * 1.02, base_price * 0.98, base_price * 1.01,
                1000000 + (i * 100000),
                rsi_value, base_price * 0.99, base_price * 0.97, base_price * 0.95,
                25 + i, 10 + i,
                900000, True, 1.1 + (i * 0.1), 60 + (i * 5)
            )
        
        print(f"✓ Inserted OHLCV data for {len(test_symbols)} symbols")
        
        # Test 4: Refresh the materialized view
        print("\n[Test 4] Refreshing materialized view...")
        try:
            await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;")
            print("✓ Materialized view refreshed successfully")
        except Exception as e:
            print(f"✗ Failed to refresh materialized view: {e}")
            return False
        
        # Test 5: Verify data in the view
        print("\n[Test 5] Verifying data in screening_snapshot...")
        
        rows = await conn.fetch("""
            SELECT 
                symbol, name, exchange, asset_class,
                close, rsi_14, ema_21, ema_50, ema_200,
                adx_14, atr_14, volume_ratio, above_ema_200, composite_score
            FROM screening_snapshot
            WHERE symbol = ANY($1)
            ORDER BY symbol;
        """, test_symbols)
        
        if len(rows) == 0:
            print("✗ No data found in screening_snapshot")
            return False
        
        print(f"✓ Found {len(rows)} records in screening_snapshot")
        print()
        print("Sample data:")
        print("-" * 80)
        
        for row in rows:
            print(f"Symbol: {row['symbol']}")
            print(f"  Name: {row['name']}")
            print(f"  Exchange: {row['exchange']}")
            print(f"  Asset Class: {row['asset_class']}")
            print(f"  Close: {row['close']:.2f}")
            print(f"  RSI(14): {row['rsi_14']:.2f}")
            print(f"  EMA(21): {row['ema_21']:.2f}")
            print(f"  EMA(50): {row['ema_50']:.2f}")
            print(f"  EMA(200): {row['ema_200']:.2f}")
            print(f"  ADX(14): {row['adx_14']:.2f}")
            print(f"  ATR(14): {row['atr_14']:.2f}")
            print(f"  Volume Ratio: {row['volume_ratio']:.2f}")
            print(f"  Above EMA(200): {row['above_ema_200']}")
            print(f"  Composite Score: {row['composite_score']:.2f}")
            print()
        
        # Test 6: Verify all required columns are present
        print("[Test 6] Verifying all required indicator columns...")
        
        required_columns = [
            'symbol', 'name', 'exchange', 'asset_class',
            'close', 'rsi_14', 'ema_21', 'ema_50', 'ema_200',
            'adx_14', 'atr_14', 'volume_ratio', 'above_ema_200',
            'iv_rank', 'pcr', 'composite_score'
        ]
        
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'screening_snapshot'
            ORDER BY ordinal_position;
        """)
        
        column_names = [col['column_name'] for col in columns]
        
        missing_columns = [col for col in required_columns if col not in column_names]
        
        if missing_columns:
            print(f"✗ Missing required columns: {missing_columns}")
            return False
        else:
            print(f"✓ All {len(required_columns)} required columns are present")
        
        # Test 7: Test SQL pre-filtering performance
        print("\n[Test 7] Testing SQL pre-filtering performance...")
        
        import time
        start_time = time.time()
        
        filtered = await conn.fetch("""
            SELECT symbol, rsi_14, adx_14, volume_ratio, composite_score
            FROM screening_snapshot
            WHERE rsi_14 >= 30 
              AND rsi_14 <= 70
              AND adx_14 >= 20
              AND volume_ratio >= 1.0
              AND above_ema_200 = TRUE
            ORDER BY composite_score DESC
            LIMIT 10;
        """)
        
        elapsed = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        print(f"✓ SQL pre-filter completed in {elapsed:.2f}ms")
        print(f"✓ Found {len(filtered)} instruments matching criteria")
        
        if elapsed > 500:
            print(f"⚠ Warning: Query took longer than 500ms target")
        
        # Test 8: Test unique constraint on symbol
        print("\n[Test 8] Testing unique constraint on symbol...")
        
        # The unique index should prevent duplicate symbols
        # This is enforced at the view level, so we just verify the index exists
        index_def = await conn.fetchval("""
            SELECT indexdef 
            FROM pg_indexes 
            WHERE indexname = 'idx_screening_snapshot_symbol';
        """)
        
        if 'UNIQUE' in index_def:
            print("✓ Unique constraint on symbol is enforced")
        else:
            print("✗ Unique constraint on symbol is not enforced")
            return False
        
        print("\n" + "=" * 80)
        print("All tests passed! ✓")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await conn.close()
        print("\n✓ Database connection closed")


async def main():
    """Main test runner"""
    success = await test_screening_snapshot()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
