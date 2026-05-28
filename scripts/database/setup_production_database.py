"""
Production Database Setup Script
Sets up Supabase PostgreSQL database for production deployment
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.database.session import AsyncSessionLocal, engine
from shared.database.models import Base
from scripts.seed_analysis_types import seed_analysis_types


async def setup_production_database():
    """Complete production database setup"""
    print("SignalixAI AI - Production Database Setup")
    print("=" * 60)
    print(f"Environment: PRODUCTION")
    print(f"Database: Supabase PostgreSQL")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Step 1: Test Connection
        print("\n1. Testing Supabase connection...")
        async with engine.begin() as conn:
            result = await conn.execute("SELECT version()")
            version = result.scalar()
            print(f"Connected to: {version}")
        
        # Step 2: Create All Tables
        print("\n2. Creating database tables...")
        async with engine.begin() as conn:
            # Drop all tables first (for clean setup)
            await conn.run_sync(Base.metadata.drop_all)
            print("   Dropped existing tables")
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            print("   Created all tables")
        
        # Step 3: Verify Tables
        print("\n3. Verifying table creation...")
        async with AsyncSessionLocal() as session:
            # Check each table
            tables_to_check = [
                'users', 'user_risk_profiles', 'subscriptions', 'analyses',
                'analysis_types', 'positions', 'trades', 'watchlists',
                'behavioral_signals', 'signal_feedback', 'order_audit_logs',
                'alert_configs', 'telegram_connections'
            ]
            
            for table in tables_to_check:
                try:
                    result = await session.execute(f"SELECT COUNT(*) FROM {table}")
                    count = result.scalar()
                    print(f"   OK {table}: {count} records")
                except Exception as e:
                    print(f"   ERROR {table}: Error - {e}")
                    return False
        
        # Step 4: Seed Initial Data
        print("\n4. Seeding initial data...")
        await seed_analysis_types()
        print("   Analysis types seeded")
        
        # Step 5: Create Indexes for Performance
        print("\n5. Creating performance indexes...")
        async with engine.begin() as conn:
            # User email index (for login)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            
            # Analysis user_id index (for user queries)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
            
            # Position user_id index (for portfolio queries)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions(user_id)")
            
            # Trade user_id index (for trade history)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)")
            
            # Watchlist user_id index (for watchlist queries)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id)")
            
            print("   Performance indexes created")
        
        # Step 6: Final Verification
        print("\n6. Final verification...")
        async with AsyncSessionLocal() as session:
            # Test user operations
            result = await session.execute("SELECT COUNT(*) FROM users")
            user_count = result.scalar()
            
            # Test analysis types
            result = await session.execute("SELECT COUNT(*) FROM analysis_types")
            analysis_type_count = result.scalar()
            
            print(f"   Users table: {user_count} records")
            print(f"   Analysis types: {analysis_type_count} records")
        
        print("\n" + "=" * 60)
        print("PRODUCTION DATABASE SETUP COMPLETE!")
        print("Supabase PostgreSQL configured")
        print("All 13 tables created")
        print("Performance indexes added")
        print("Initial data seeded")
        print("Ready for authentication flow")
        print("=" * 60)
        
        print("\nNext Steps:")
        print("1. Start auth service: python services/auth-service/main.py")
        print("2. Test authentication: python scripts/test_auth_flow.py")
        print("3. Deploy to production")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(setup_production_database())
    
    if success:
        print("\n✅ Database setup successful!")
        sys.exit(0)
    else:
        print("\n❌ Database setup failed!")
        sys.exit(1)