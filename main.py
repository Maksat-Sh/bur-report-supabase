import os
import ssl
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# ✅ правильный SSL-контекст
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={
        "ssl": ssl_context
    }
)

app = FastAPI()

@app.on_event("startup")
async def startup():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

@app.get("/")
async def root():
    return {"status": "ok", "db": "connected"}
