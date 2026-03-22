import asyncio
import os
from src.database import DatabaseManager
from sqlalchemy import text

async def check():
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/pocketoption")
    dm = DatabaseManager(db_url)
    async with dm.get_session() as s:
        r = await s.execute(text("SELECT user_id, amount_current, soros_level, consecutive_wins, consecutive_losses FROM autotrade_session_state WHERE user_id::text LIKE '94736c7d%'"))
        rows = r.fetchall()
        if not rows:
            print("Nenhum estado de sessão encontrado")
        for row in rows:
            print(f"user_id: {row[0]}")
            print(f"amount_current: {row[1]}")
            print(f"soros_level: {row[2]}")
            print(f"consecutive_wins: {row[3]}")
            print(f"consecutive_losses: {row[4]}")

asyncio.run(check())
