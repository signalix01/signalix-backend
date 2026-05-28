"""
Create Test User
Creates a test user with complete profile for development/testing
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.settings import settings
from shared.database.models import User, UserRiskProfile, Subscription
import bcrypt


async def create_test_user():
    """Create test user with complete profile"""
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("👤 Creating test user...")
            
            # Check if test user already exists
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == "test@signalixai.com")
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print("  ⏭️  Test user already exists")
                print(f"  📧 Email: test@signalixai.com")
                print(f"  🔑 Password: Test123")
                return
            
            # Hash password using bcrypt directly
            password_hash = bcrypt.hashpw("Test123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Create user (Tier 1)
            user = User(
                email="test@signalixai.com",
                phone="+919876543210",
                password_hash=password_hash,
                full_name="Test User",
                country_of_residence="IN",
                declared_trading_capital_inr=50000000,  # ₹5L in paise
                risk_tolerance_score=7,
                investment_horizon="swing",
                sebi_declaration_acknowledged=True,
                email_verified=True,
                phone_verified=True
            )
            session.add(user)
            await session.flush()
            
            print(f"  ✅ User created: {user.email}")
            
            # Create risk profile (Tier 2)
            risk_profile = UserRiskProfile(
                user_id=user.id,
                annual_income_range="15-50L",
                emergency_fund_months=6,
                existing_portfolio_value_inr=20000000,  # ₹2L in paise
                current_sector_exposure={"IT": 30, "Banking": 20, "Auto": 15},
                preferred_markets=["NSE_EQ", "NSE_FO"],
                avg_trade_duration="swing",
                max_position_size_pct=8,
                notification_channels=["email", "whatsapp"],
                alert_confidence_threshold=7,
                preferred_analysis_depth="shallow",
                language_preference="en",
                wizard_completed=True,
                wizard_completed_at=datetime.utcnow()
            )
            session.add(risk_profile)
            
            print(f"  ✅ Risk profile created (Tier 2 complete)")
            
            # Create subscription (Premium tier)
            subscription = Subscription(
                user_id=user.id,
                tier='premium',
                status='active',
                analyses_limit=30,
                analyses_used=0,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            session.add(subscription)
            
            print(f"  ✅ Subscription created (Premium - 30 analyses/month)")
            
            await session.commit()
            
            print("\n✅ Test user created successfully!")
            print("\n📋 Login Credentials:")
            print("  📧 Email: test@signalixai.com")
            print("  🔑 Password: Test123")
            print("\n📊 Profile:")
            print(f"  💰 Capital: ₹5,00,000")
            print(f"  📈 Risk Tolerance: 7/10")
            print(f"  ⏱️  Horizon: Swing Trading")
            print(f"  🎯 Subscription: Premium (30 analyses/month)")
            
        except Exception as e:
            print(f"\n❌ Error creating test user: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("SignalixAI AI - Create Test User")
    print("=" * 60)
    print()
    
    asyncio.run(create_test_user())
