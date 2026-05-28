import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.options_analytics.models.options_models import OptionsChain, OptionStrike, Base
from shared.config.settings import settings

async def seed_data():
    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        
    engine = create_async_engine(db_url, echo=False)
    
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        symbol = "NIFTY"
        # Find next Thursday for expiry
        today = date.today()
        days_ahead = 3 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        expiry_date = today + timedelta(days=days_ahead)
        
        spot_price = 22500.0
        
        # Create chain
        chain = OptionsChain(
            symbol=symbol,
            expiry_date=expiry_date,
            spot_price=spot_price,
            underlying_price=spot_price,
            timestamp=datetime.utcnow(),
            total_call_oi=1000000,
            total_put_oi=1200000,
            total_call_volume=500000,
            total_put_volume=600000,
            pcr_oi=1.2,
            pcr_volume=1.2
        )
        session.add(chain)
        await session.flush()
        
        # Create strikes
        strikes = []
        for i in range(-20, 21):
            strike_price = spot_price + (i * 50)
            
            # Simple pricing model
            distance = abs(i * 50)
            call_price = max(0.5, 400 - distance + random.uniform(-10, 10)) if i <= 0 else max(0.5, 200 - distance + random.uniform(-5, 5))
            put_price = max(0.5, 400 - distance + random.uniform(-10, 10)) if i >= 0 else max(0.5, 200 - distance + random.uniform(-5, 5))
            
            strike = OptionStrike(
                chain_id=chain.id,
                strike_price=strike_price,
                call_ltp=call_price,
                call_oi=random.randint(10000, 150000),
                call_volume=random.randint(5000, 50000),
                call_iv=random.uniform(0.12, 0.25),
                call_delta=0.5 - (i * 0.02),
                call_gamma=0.002,
                put_ltp=put_price,
                put_oi=random.randint(10000, 150000),
                put_volume=random.randint(5000, 50000),
                put_iv=random.uniform(0.12, 0.25),
                put_delta=-0.5 - (i * 0.02),
                put_gamma=0.002,
            )
            strikes.append(strike)
            
        session.add_all(strikes)
        await session.commit()
        print(f"Seeded Options Chain for {symbol} with {len(strikes)} strikes. Expiry: {expiry_date}")

if __name__ == "__main__":
    asyncio.run(seed_data())
