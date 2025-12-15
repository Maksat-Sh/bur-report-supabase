import os
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=0,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

app = FastAPI()


@app.on_event("startup")
async def startup():
    # ⚠️ НЕ создаём таблицы автоматически
    # Просто проверяем соединение
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@app.get("/")
async def root():
    return {"status": "ok"}
