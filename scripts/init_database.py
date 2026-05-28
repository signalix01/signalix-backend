"""
Initialize Database
Creates all tables and seeds initial data
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.models import Base
from shared.database.session import engine
from scripts.seed_analysis_types import seed_analysis_types


async def init_database():
    """Initialize database with tables and seed data"""
    try:
        print("=" * 60)
        print("SignalixAI AI - Database Initialization")
        print("=" * 60)
        print()
        
        # Create all tables
        print("📊 Creating database tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Tables created successfully!")
        print()
        
        # Seed analysis types
        await seed_analysis_types()
        print()
        
        print("=" * 60)
        print("✅ Database initialization complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error initializing database: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
