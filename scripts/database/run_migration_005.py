"""
Script to run migration 005 (screening_snapshot materialized view)

This script manually applies the migration without requiring alembic CLI.
"""
import asyncio
import sys
from dotenv import load_dotenv
import os
import asyncpg

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)

# Convert asyncpg URL format
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')


async def run_migration():
    """Run the migration to create screening_snapshot materialized view"""
    
    print("=" * 80)
    print("Running Migration 005: Create screening_snapshot Materialized View")
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
        # Check if TimescaleDB extension is available
        print("\n[Step 1] Checking TimescaleDB extension...")
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                );
            """)
            
            if result:
                print("✓ TimescaleDB extension is installed")
            else:
                print("⚠ TimescaleDB extension is not installed")
                print("  Note: Hypertable features will not be available")
        except Exception as e:
            print(f"⚠ Could not check TimescaleDB: {e}")
        
        # Step 2: Create instruments table if not exists
        print("\n[Step 2] Creating instruments table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS instruments (
                symbol VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255),
                exchange VARCHAR(20),
                asset_class VARCHAR(20),
                sector VARCHAR(100),
                industry VARCHAR(100),
                market_cap_cr FLOAT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("✓ instruments table ready")
        
        # Step 3: Create ohlcv_1d table if not exists
        print("\n[Step 3] Creating ohlcv_1d table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_1d (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                symbol VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open FLOAT NOT NULL,
                high FLOAT NOT NULL,
                low FLOAT NOT NULL,
                close FLOAT NOT NULL,
                volume FLOAT NOT NULL,
                
                -- Technical indicators
                rsi_14 FLOAT,
                ema_21 FLOAT,
                ema_50 FLOAT,
                ema_200 FLOAT,
                sma_20 FLOAT,
                adx_14 FLOAT,
                atr_14 FLOAT,
                volume_ma_20 FLOAT,
                
                -- F&O specific indicators
                iv_rank FLOAT,
                pcr FLOAT,
                oi FLOAT,
                oi_change FLOAT,
                
                -- Derived fields
                above_ema_200 BOOLEAN,
                volume_ratio FLOAT,
                composite_score FLOAT,
                
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("✓ ohlcv_1d table ready")
        
        # Step 4: Create index on ohlcv_1d
        print("\n[Step 4] Creating index on ohlcv_1d...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ohlcv_1d_symbol_timestamp 
            ON ohlcv_1d (symbol, timestamp DESC);
        """)
        print("✓ Index created on ohlcv_1d")
        
        # Step 5: Try to convert ohlcv_1d to hypertable (if TimescaleDB is available)
        print("\n[Step 5] Converting ohlcv_1d to hypertable...")
        try:
            await conn.execute("""
                SELECT create_hypertable('ohlcv_1d', 'timestamp', 
                                         chunk_time_interval => INTERVAL '7 days',
                                         if_not_exists => TRUE);
            """)
            print("✓ ohlcv_1d converted to TimescaleDB hypertable")
        except Exception as e:
            print(f"⚠ Could not convert to hypertable (TimescaleDB may not be available): {e}")
            print("  Continuing with regular table...")
        
        # Step 6: Create the screening_snapshot materialized view
        print("\n[Step 6] Creating screening_snapshot materialized view...")
        
        # Drop if exists (for idempotency)
        await conn.execute("DROP MATERIALIZED VIEW IF EXISTS screening_snapshot;")
        
        await conn.execute("""
            CREATE MATERIALIZED VIEW screening_snapshot AS
            WITH latest_ohlcv AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    rsi_14,
                    ema_21,
                    ema_50,
                    ema_200,
                    sma_20,
                    adx_14,
                    atr_14,
                    volume_ma_20,
                    iv_rank,
                    pcr,
                    oi,
                    oi_change,
                    above_ema_200,
                    volume_ratio,
                    composite_score
                FROM ohlcv_1d
                ORDER BY symbol, timestamp DESC
            )
            SELECT 
                i.symbol,
                i.name,
                i.exchange,
                i.asset_class,
                i.sector,
                i.industry,
                i.market_cap_cr,
                o.timestamp AS last_updated,
                o.open,
                o.high,
                o.low,
                o.close,
                o.volume,
                o.rsi_14,
                o.ema_21,
                o.ema_50,
                o.ema_200,
                o.sma_20,
                o.adx_14,
                o.atr_14,
                o.volume_ma_20,
                o.iv_rank,
                o.pcr,
                o.oi,
                o.oi_change,
                o.above_ema_200,
                o.volume_ratio,
                o.composite_score
            FROM instruments i
            LEFT JOIN latest_ohlcv o ON i.symbol = o.symbol
            WHERE i.is_active = TRUE;
        """)
        print("✓ screening_snapshot materialized view created")
        
        # Step 7: Create unique index on symbol
        print("\n[Step 7] Creating unique index on symbol...")
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_screening_snapshot_symbol 
            ON screening_snapshot (symbol);
        """)
        print("✓ Unique index on symbol created")
        
        # Step 8: Create additional performance indexes
        print("\n[Step 8] Creating performance indexes...")
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_snapshot_rsi 
            ON screening_snapshot (rsi_14) WHERE rsi_14 IS NOT NULL;
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_snapshot_adx 
            ON screening_snapshot (adx_14) WHERE adx_14 IS NOT NULL;
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_snapshot_volume_ratio 
            ON screening_snapshot (volume_ratio) WHERE volume_ratio IS NOT NULL;
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_snapshot_composite 
            ON screening_snapshot (composite_score DESC) WHERE composite_score IS NOT NULL;
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_snapshot_asset_class 
            ON screening_snapshot (asset_class);
        """)
        
        print("✓ Performance indexes created")
        
        # Step 9: Create refresh function
        print("\n[Step 9] Creating refresh function...")
        await conn.execute("""
            CREATE OR REPLACE FUNCTION refresh_screening_snapshot()
            RETURNS void AS $$
            BEGIN
                REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("✓ Refresh function created")
        
        # Step 10: Update alembic version (if alembic_version table exists)
        print("\n[Step 10] Updating alembic version...")
        try:
            # Check if alembic_version table exists
            exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                );
            """)
            
            if exists:
                await conn.execute("""
                    UPDATE alembic_version SET version_num = '005';
                """)
                print("✓ Alembic version updated to 005")
            else:
                print("⚠ alembic_version table not found, skipping version update")
        except Exception as e:
            print(f"⚠ Could not update alembic version: {e}")
        
        print("\n" + "=" * 80)
        print("Migration 005 completed successfully! ✓")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Run: python tests/test_screening_snapshot.py")
        print("2. Configure automatic refresh (see README_005.md)")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n✗ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await conn.close()
        print("\n✓ Database connection closed")


async def main():
    """Main runner"""
    success = await run_migration()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
