import asyncio
from shared.database.session import AsyncSessionLocal
from shared.database.models import User
from sqlalchemy import select

async def check_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.email, User.email_verified, User.password_hash))
        users = result.all()
        print(f"\nFound {len(users)} users:")
        for email, verified, pwd_hash in users:
            print(f"  - {email} (verified: {verified}) - hash: {pwd_hash[:50]}...")

asyncio.run(check_users())
