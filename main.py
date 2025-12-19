import os
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}

# ✅ Проверка БД вручную, а не в startup
@app.get("/db-check")
async def db_check():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"db": "connected"}
