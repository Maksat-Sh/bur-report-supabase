import os
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlalchemy.pool import NullPool

# =========================
# DATABASE
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# asyncpg + SSL (ОБЯЗАТЕЛЬНО для Render)
DATABASE_URL_ASYNC = DATABASE_URL.replace(
    "postgresql://",
    "postgresql+asyncpg://"
)

engine = create_async_engine(
    DATABASE_URL_ASYNC,
    echo=False,
    poolclass=NullPool,  # важно для бесплатного Render
    connect_args={
        "ssl": "require"
    }
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# =========================
# APP
# =========================

app = FastAPI()


@app.on_event("startup")
async def startup():
    """
    Проверяем подключение к БД.
    Соединение НЕ держим.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ Database connected successfully")
    except Exception as e:
        print("❌ Database connection failed:", e)
        raise


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()


# =========================
# TEST ROUTE
# =========================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Render + PostgreSQL works"}


@app.get("/db-test")
async def db_test():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT now()"))
        return {"time": str(result.scalar())}
