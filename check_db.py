import asyncio
from shared.database.session import engine
from sqlalchemy import text

async def check():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'positions'"))
        cols = [r[0] for r in res]
        print(f"Columns in positions table: {cols}")
        
if __name__ == "__main__":
    asyncio.run(check())
