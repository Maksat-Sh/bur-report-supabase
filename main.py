import os
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import io

# =========================
# ENV
# =========================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
Base = declarative_base()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# DB
# =========================
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


# =========================
# MODELS
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)  # dispatcher / driller


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    area = Column(String)
    rig_number = Column(String)
    meterage = Column(String)
    pogon = Column(String)
    operation = Column(String)
    responsible = Column(String)
    note = Column(Text)


# =========================
# Startup — create tables
# =========================
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# =========================
# SCHEMAS
# =========================
class Login(BaseModel):
    username: str
    password: str


class ReportIn(BaseModel):
    area: str
    rig_number: str
    meterage: str
    pogon: str
    operation: str
    responsible: str
    note: str


# =========================
# AUTH
# =========================
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def hash_password(password):
    return pwd_context.hash(password)


@app.post("/login")
async def login(data: Login, db: AsyncSession = Depends(get_db)):
    q = await db.execute(
        User.__table__.select().where(User.username == data.username)
    )
    user = q.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="Неправильные логин или пароль")

    user = user[0]

    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=400, detail="Неправильные логин или пароль")

    return {"message": "success", "role": user.role}


# =========================
# Dispatcher creates users
# =========================
@app.post("/create_user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    hashed = hash_password(password)

    new_user = User(username=username, password=hashed, role=role)
    db.add(new_user)
    await db.commit()
    return {"message": "Пользователь создан"}


# =========================
# Reports
# =========================
@app.post("/report")
async def submit_report(data: ReportIn, db: AsyncSession = Depends(get_db)):
    report = Report(**data.dict())
    db.add(report)
    await db.commit()
    return {"message": "Report submitted successfully"}


@app.get("/reports")
async def get_reports(db: AsyncSession = Depends(get_db)):
    q = await db.execute(Report.__table__.select())
    return q.fetchall()


# =========================
# Excel Export
# =========================
@app.get("/export")
async def export_excel(db: AsyncSession = Depends(get_db)):
    q = await db.execute(Report.__table__.select())
    rows = q.fetchall()

    df = pd.DataFrame([
        {
            "ID": r.id,
            "Дата": r.created_at,
            "Участок": r.area,
            "Агрегат": r.rig_number,
            "Метраж": r.meterage,
            "Погонометр": r.pogon,
            "Операция": r.operation,
            "Ответственный": r.responsible,
            "Примечание": r.note,
        }
        for r in rows
    ])

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)

    return FileResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="reports.xlsx",
    )


# =========================
# Static dispatcher page
# =========================
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/dispatcher.html", "r", encoding="utf-8") as f:
        return f.read()
