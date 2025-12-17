import os
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import text

# ========================
# DATABASE
# ========================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set")

# Render требует SSL
DATABASE_URL = DATABASE_URL.replace(
    "postgresql://",
    "postgresql+asyncpg://"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "ssl": "require"   # 🔥 КЛЮЧЕВОЙ МОМЕНТ
    },
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass


# ========================
# FASTAPI
# ========================

app = FastAPI()


@app.on_event("startup")
async def startup():
    """
    Минимальная проверка соединения.
    Никаких create_all, никаких begin()
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ Database connected")
    except Exception as e:
        print("❌ Database connection failed:", e)
        raise


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()


# ========================
# ROUTES
# ========================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Render + PostgreSQL works"}
