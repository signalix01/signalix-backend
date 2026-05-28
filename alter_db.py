import asyncio
from shared.database.session import engine
from sqlalchemy import text

async def alter():
    async with engine.begin() as conn:
        try:
            await conn.execute(text('ALTER TABLE positions ADD COLUMN portfolio_id UUID'))
            print("Added portfolio_id")
        except Exception as e:
            print(f"Error adding portfolio_id: {e}")
            
if __name__ == "__main__":
    asyncio.run(alter())
