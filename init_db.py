import asyncio
from shared.database.session import engine
from shared.database.models import Base
from shared.database.user_models import User, Watchlist, WatchlistInstrument
from shared.database.portfolio_models import Portfolio, Position
from shared.database.execution_models import Order

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")

if __name__ == "__main__":
    asyncio.run(init())
