from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
   connect_args={"ssl": "require"},
    echo=False
)

Base = declarative_base()


async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db():
    async with async_session() as session:
        yield session

class DrillingReport(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    area = Column(String)
    rig_number = Column(String)
    meterage = Column(Float)
    running_meter = Column(Float)
    operations = Column(String)
    responsible = Column(String)
    note = Column(String)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app = FastAPI()


@app.on_event("startup")
async def on_start():
    await init_models()


templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.post("/api/report")
async def create_report(data: dict, db: AsyncSession = Depends(get_db)):
    report = DrillingReport(**data)
    db.add(report)
    await db.commit()
    return {"message": "Report saved"}


@app.get("/api/reports")
async def all_reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute("SELECT * FROM reports ORDER BY datetime DESC")
    rows = result.fetchall()
    return [dict(row) for row in rows]
