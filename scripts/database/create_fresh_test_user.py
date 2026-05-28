import asyncio
from shared.database.session import AsyncSessionLocal
from shared.database.models import User
from sqlalchemy import select
import bcrypt
import uuid

async def create_test_user():
    email = "testuser@signalixai.com"
    password = "TestPassword123!"
    
    # Hash password
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    async with AsyncSessionLocal() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"User {email} already exists. Updating password...")
            existing_user.password_hash = password_hash
            existing_user.email_verified = True
        else:
            print(f"Creating new user {email}...")
            user = User(
                id=uuid.uuid4(),
                email=email,
                phone="+919999999999",
                password_hash=password_hash,
                full_name="Test User",
                country_of_residence="IN",
                declared_trading_capital_inr=100000_00,  # 1 lakh in paise
                risk_tolerance_score=5,
                investment_horizon="swing",
                sebi_declaration_acknowledged=True,
                email_verified=True,
                phone_verified=True
            )
            session.add(user)
        
        await session.commit()
        print(f"\n✓ User created/updated successfully!")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
        print(f"  Password Hash: {password_hash[:50]}...")

asyncio.run(create_test_user())
