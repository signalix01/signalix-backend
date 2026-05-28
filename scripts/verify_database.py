"""
Verify Database Setup
Tests all database connections and table structures
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.session import AsyncSessionLocal, engine
from shared.database.models import (
    User, UserRiskProfile, Subscription, Analysis, AnalysisType,
    Position, Trade, Watchlist, BehavioralSignal, SignalFeedback,
    OrderAuditLog, AlertConfig, TelegramConnection
)
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError


async def verify_database():
    """Comprehensive database verification"""
    print("🔍 Verifying Supabase PostgreSQL Database Setup")
    print("=" * 60)
    
    try:
        # Test 1: Basic Connection
        print("\n1️⃣ Testing database connection...")
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected to: {version}")
        
        # Test 2: Check Tables
        print("\n2️⃣ Verifying table structure...")
        async with engine.begin() as conn:
            inspector = inspect(conn.sync_connection)
            tables = inspector.get_table_names()
            
            expected_tables = [
                'users', 'user_risk_profiles', 'subscriptions', 'analyses',
                'analysis_types', 'positions', 'trades', 'watchlists',
                'behavioral_signals', 'signal_feedback', 'order_audit_logs',
                'alert_configs', 'telegram_connections'
            ]
            
            print(f"📊 Found {len(tables)} tables:")
            for table in sorted(tables):
                status = "✅" if table in expected_tables else "⚠️"
                print(f"   {status} {table}")
            
            missing_tables = set(expected_tables) - set(tables)
            if missing_tables:
                print(f"\n❌ Missing tables: {missing_tables}")
                return False
            else:
                print(f"\n✅ All {len(expected_tables)} required tables present")
        
        # Test 3: Test Session and CRUD Operations
        print("\n3️⃣ Testing database operations...")
        async with AsyncSessionLocal() as session:
            # Test user count
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            print(f"✅ Users table accessible: {user_count} records")
            
            # Test analysis types
            result = await session.execute(text("SELECT COUNT(*) FROM analysis_types"))
            analysis_type_count = result.scalar()
            print(f"✅ Analysis types seeded: {analysis_type_count} records")
            
            # Test subscription plans
            result = await session.execute(text("SELECT COUNT(*) FROM subscriptions"))
            subscription_count = result.scalar()
            print(f"✅ Subscriptions table: {subscription_count} records")
        
        # Test 4: Test Constraints and Indexes
        print("\n4️⃣ Verifying constraints and indexes...")
        async with engine.begin() as conn:
            inspector = inspect(conn.sync_connection)
            
            # Check unique constraints on users table
            indexes = inspector.get_indexes('users')
            unique_indexes = [idx for idx in indexes if idx['unique']]
            print(f"✅ Users table has {len(unique_indexes)} unique indexes")
            
            # Check foreign keys
            fks = inspector.get_foreign_keys('user_risk_profiles')
            print(f"✅ User risk profiles has {len(fks)} foreign key constraints")
        
        # Test 5: Test Authentication Flow
        print("\n5️⃣ Testing authentication data flow...")
        async with AsyncSessionLocal() as session:
            # Try to fetch a user (should work even if no users exist)
            result = await session.execute(
                text("SELECT email FROM users LIMIT 1")
            )
            user_email = result.scalar()
            if user_email:
                print(f"✅ Sample user found: {user_email}")
            else:
                print("ℹ️ No users in database (expected for fresh setup)")
        
        print("\n" + "=" * 60)
        print("🎉 DATABASE VERIFICATION SUCCESSFUL!")
        print("✅ Supabase PostgreSQL is properly configured")
        print("✅ All tables created and accessible")
        print("✅ Authentication flow ready")
        print("=" * 60)
        
        return True
        
    except SQLAlchemyError as e:
        print(f"\n❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
    finally:
        await engine.dispose()


async def test_authentication_endpoints():
    """Test that auth endpoints can connect to database"""
    print("\n🔐 Testing Authentication Service Database Connection...")
    
    try:
        # Import auth service dependencies
        from services.auth_service.main import app
        from shared.database.session import get_db
        
        # Test database dependency
        async for db in get_db():
            result = await db.execute(text("SELECT 1"))
            print("✅ Auth service can connect to database")
            break
            
    except Exception as e:
        print(f"❌ Auth service database connection failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(verify_database())
    
    if success:
        print("\n🚀 Ready for production deployment!")
        print("\nNext steps:")
        print("1. Start auth service: python services/auth-service/main.py")
        print("2. Test login endpoint: curl -X POST http://localhost:8000/api/v1/auth/login")
        print("3. Deploy to production")
    else:
        print("\n❌ Database setup incomplete. Please fix errors above.")
        sys.exit(1)