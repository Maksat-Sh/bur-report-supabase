import os
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

app = FastAPI()


@app.on_event("startup")
async def startup():
    # минимальная проверка, БЕЗ создания таблиц
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("✅ Database connected")


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    print("🛑 Database disconnected")


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/db-check")
async def db_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "detail": str(e)}
