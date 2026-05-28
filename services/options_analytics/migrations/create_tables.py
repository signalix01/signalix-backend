"""
Options Analytics Database Migration

Creates tables for options chain data, Greeks, Max Pain, GEX, and OI tracking.
Run this migration to set up the Options Analytics schema.
"""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from services.options_analytics.models.options_models import Base

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")


async def create_tables():
    """Create all Options Analytics tables"""
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        print("✓ Options Analytics tables created successfully")
        print("  - options_chains")
        print("  - option_strikes")
        print("  - greeks_cache")
        print("  - options_strategies")
        print("  - strategy_legs")
        print("  - max_pain_results")
        print("  - gex_results")
        print("  - oi_changes")
        print("  - historical_options_data")
    
    await engine.dispose()


async def create_indexes():
    """Create additional indexes for performance"""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        indexes = [
            """
            CREATE INDEX IF NOT EXISTS idx_options_chain_latest 
            ON options_chains(symbol, expiry_date, timestamp DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_greeks_latest 
            ON greeks_cache(symbol, strike_price, option_type, expiry_date, calculated_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_max_pain_latest 
            ON max_pain_results(symbol, expiry_date, calculated_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gex_latest 
            ON gex_results(symbol, expiry_date, calculated_at DESC)
            """,
        ]
        
        for idx_sql in indexes:
            await conn.execute(text(idx_sql))
        
        print("✓ Additional indexes created")
    
    await engine.dispose()


async def drop_tables():
    """Drop all Options Analytics tables (use with caution)"""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("✓ Options Analytics tables dropped")
    
    await engine.dispose()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        print("⚠️  Dropping all Options Analytics tables...")
        asyncio.run(drop_tables())
    else:
        print("🚀 Creating Options Analytics tables...")
        asyncio.run(create_tables())
        asyncio.run(create_indexes())
        print("\n✅ Migration complete!")
