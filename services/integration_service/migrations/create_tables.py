"""
Integration Service Database Migration

Creates tables for webhook processing, signals, and logs.
Run this migration to set up the Integration Service schema.
"""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from services.integration_service.models.webhook_models import Base

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")


async def create_tables():
    """Create all Integration Service tables"""
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        print("✓ Integration Service tables created successfully")
        print("  - webhook_configs")
        print("  - signals")
        print("  - webhook_logs")
        print("  - dead_letter_webhooks")
    
    await engine.dispose()


async def create_indexes():
    """Create additional indexes for performance"""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Additional indexes for common queries
        indexes = [
            """
            CREATE INDEX IF NOT EXISTS idx_signals_created_at 
            ON signals(created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_webhook_logs_timestamp 
            ON webhook_logs(received_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_dead_letter_failed_at 
            ON dead_letter_webhooks(failed_at DESC)
            """,
        ]
        
        for idx_sql in indexes:
            await conn.execute(text(idx_sql))
        
        print("✓ Additional indexes created")
    
    await engine.dispose()


async def drop_tables():
    """Drop all Integration Service tables (use with caution)"""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("✓ Integration Service tables dropped")
    
    await engine.dispose()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        print("⚠️  Dropping all Integration Service tables...")
        asyncio.run(drop_tables())
    else:
        print("🚀 Creating Integration Service tables...")
        asyncio.run(create_tables())
        asyncio.run(create_indexes())
        print("\n✅ Migration complete!")
