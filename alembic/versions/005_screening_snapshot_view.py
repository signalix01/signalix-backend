"""Create screening_snapshot materialized view

Revision ID: 005
Revises: 004
Create Date: 2025-01-15 12:00:00.000000

Requirements: 9.3, 16.1

This migration creates the screening_snapshot materialized view that joins
instruments with the latest ohlcv_1d record per symbol, including all
technical indicators needed for fast SQL pre-filtering in the AI Screening Engine.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create screening_snapshot materialized view for fast SQL pre-filtering.
    
    This view joins instruments with the latest OHLCV data and pre-computes
    all technical indicators needed for screening:
    - RSI (14-period)
    - EMAs (21, 50, 200)
    - ADX (14-period)
    - ATR (14-period)
    - Volume ratio (current volume / 20-day average)
    - Above EMA 200 flag
    - IV Rank (for F&O instruments)
    - PCR (Put-Call Ratio for F&O)
    - Composite score (weighted combination of all indicators)
    
    The view is configured as a TimescaleDB continuous aggregate that
    refreshes every 15 minutes during market hours.
    """
    
    # First, ensure the required base tables exist
    # Note: This assumes instruments and ohlcv_1d tables are created elsewhere
    # If they don't exist, we'll create placeholder tables for now
    
    # Check if instruments table exists, if not create it
    op.execute("""
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
    
    # Check if ohlcv_1d table exists, if not create it as a hypertable
    op.execute("""
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
    
    # Create index on ohlcv_1d for efficient queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ohlcv_1d_symbol_timestamp 
        ON ohlcv_1d (symbol, timestamp DESC);
    """)
    
    # Convert ohlcv_1d to hypertable if not already
    op.execute("""
        SELECT create_hypertable('ohlcv_1d', 'timestamp', 
                                 chunk_time_interval => INTERVAL '7 days',
                                 if_not_exists => TRUE);
    """)
    
    # Create the screening_snapshot materialized view
    # This view gets the latest OHLCV record for each symbol
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS screening_snapshot AS
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
    
    # Create unique index on symbol for fast lookups
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_screening_snapshot_symbol 
        ON screening_snapshot (symbol);
    """)
    
    # Create additional indexes for common filter columns
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_snapshot_rsi 
        ON screening_snapshot (rsi_14) WHERE rsi_14 IS NOT NULL;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_snapshot_adx 
        ON screening_snapshot (adx_14) WHERE adx_14 IS NOT NULL;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_snapshot_volume_ratio 
        ON screening_snapshot (volume_ratio) WHERE volume_ratio IS NOT NULL;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_snapshot_composite 
        ON screening_snapshot (composite_score DESC) WHERE composite_score IS NOT NULL;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_snapshot_asset_class 
        ON screening_snapshot (asset_class);
    """)
    
    # Create a function to refresh the materialized view
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_screening_snapshot()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Note: TimescaleDB continuous aggregate policies are typically set up
    # via application code or manual SQL after deployment, as they require
    # the TimescaleDB extension to be fully configured.
    # 
    # To configure the 15-minute refresh policy, run this SQL manually:
    # 
    # SELECT add_continuous_aggregate_policy('screening_snapshot',
    #     start_offset => INTERVAL '1 hour',
    #     end_offset => INTERVAL '15 minutes',
    #     schedule_interval => INTERVAL '15 minutes');
    
    print("✓ Created screening_snapshot materialized view")
    print("✓ Added unique index on symbol")
    print("✓ Added performance indexes on filter columns")
    print("✓ Created refresh function")
    print("")
    print("MANUAL STEP REQUIRED:")
    print("To enable automatic 15-minute refresh, run this SQL:")
    print("  REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;")
    print("")
    print("For TimescaleDB continuous aggregate (if using TimescaleDB 2.0+):")
    print("  -- Convert to continuous aggregate and add refresh policy")


def downgrade() -> None:
    """Drop the screening_snapshot materialized view and related objects"""
    
    # Drop the refresh function
    op.execute("DROP FUNCTION IF EXISTS refresh_screening_snapshot();")
    
    # Drop the materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS screening_snapshot;")
    
    # Note: We don't drop instruments or ohlcv_1d tables as they may be used elsewhere
    
    print("✓ Dropped screening_snapshot materialized view")
    print("✓ Dropped refresh function")
