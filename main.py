import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, func
from dotenv import load_dotenv
import ssl

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "ssl": "require"
    }
)

async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

app = FastAPI()

# миграция
async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def on_start():
    await init_models()

@app.get("/")
async def root():
    return {"status": "ok"}

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    plot = Column(String)
    rig = Column(String)
    depth = Column(String)
    meter = Column(String)
    operation = Column(String)
    person = Column(String)
    note = Column(String)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("startup")
async def on_start():
    await init_models()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/", response_class=HTMLResponse)
async def dispatcher(request: Request):
    return RedirectResponse("/dispatcher")


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page():
    return open("dispatcher.html", encoding="utf-8").read()


@app.post("/submit")
async def submit(
        plot: str = Form(...),
        rig: str = Form(...),
        depth: str = Form(...),
        meter: str = Form(...),
        operation: str = Form(...),
        person: str = Form(...),
        note: str = Form(...),
        db: AsyncSession = Depends(get_db)
):
    rep = Report(
        plot=plot,
        rig=rig,
        depth=depth,
        meter=meter,
        operation=operation,
        person=person,
        note=note
    )
    db.add(rep)
    await db.commit()
    return {"message": "Report submitted successfully"}


@app.get("/reports")
async def get_reports(db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        Report.__table__.select().order_by(Report.id.desc())
    )
    return r.fetchall()
