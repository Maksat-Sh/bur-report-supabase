import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, select
from sqlalchemy.sql import func

import pandas as pd
from io import BytesIO

# -----------------------------
# Настройки
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise RuntimeError("DATABASE_URL не найден в .env")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -----------------------------
# Модели
# -----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String)  # driller / dispatcher


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    datetime = Column(DateTime, server_default=func.now())
    area = Column(String)
    rig_number = Column(String)
    depth = Column(Float)
    pogon = Column(Float)
    operation = Column(String)
    responsible = Column(String)
    note = Column(String)
    user_id = Column(Integer)

# -----------------------------
# Утилиты
# -----------------------------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(pwd):
    return pwd_context.hash(pwd)

# -----------------------------
# Создание таблиц
# -----------------------------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# -----------------------------
# Маршруты
# -----------------------------

# Главная — вход диспетчера
@app.get("/", response_class=HTMLResponse)
async def dispatcher_login_page(request: Request):
    return templates.TemplateResponse("dispatcher_login.html", {"request": request})

# Логин диспетчера
@app.post("/dispatcher/login")
async def dispatcher_login(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(User).where(User.username == username))
    user = q.scalars().first()

    if not user or not verify_password(password, user.password_hash) or user.role != "dispatcher":
        raise HTTPException(status_code=400, detail="Неправильные логин или пароль")

    return {"message": "dispatcher_ok"}

# Интерфейс диспетчера
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(Report).order_by(Report.id.desc()))
    reports = q.scalars().all()
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})

# Создание пользователя
@app.post("/dispatcher/create_user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    h = hash_password(password)
    user = User(username=username, password_hash=h, role=role)
    db.add(user)
    await db.commit()
    return {"message": "user_created"}

# -----------------------------
# Буровик
# -----------------------------

# Страница буровика
@app.get("/driller", response_class=HTMLResponse)
async def driller_page(request: Request):
    return templates.TemplateResponse("driller.html", {"request": request})

# Логин буровика
@app.post("/driller/login")
async def driller_login(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(User).where(User.username == username))
    user = q.scalars().first()

    if not user or not verify_password(password, user.password_hash) or user.role != "driller":
        raise HTTPException(status_code=400, detail="Неправильные логин или пароль")

    return {"message": "driller_ok", "user_id": user.id}

# Отправка отчёта
@app.post("/driller/send_report")
async def send_report(
    user_id: int = Form(...),
    area: str = Form(...),
    rig_number: str = Form(...),
    depth: float = Form(...),
    pogon: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    r = Report(
        area=area,
        rig_number=rig_number,
        depth=depth,
        pogon=pogon,
        operation=operation,
        responsible=responsible,
        note=note,
        user_id=user_id
    )
    db.add(r)
    await db.commit()
    return {"message": "ok"}

# -----------------------------
# Экспорт Excel
# -----------------------------
@app.get("/dispatcher/export")
async def export_excel(db: AsyncSession = Depends(get_db)):

    q = await db.execute(select(Report).order_by(Report.id))
    rows = q.scalars().all()

    data = []
    for r in rows:
        data.append({
            "ID": r.id,
            "Дата/время": r.datetime,
            "Участок": r.area,
            "№ бур.агрегата": r.rig_number,
            "Метраж": r.depth,
            "Погонометр": r.pogon,
            "Операция": r.operation,
            "Ответственное лицо": r.responsible,
            "Примечание": r.note,
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return FileResponse(output, media_type="application/vnd.ms-excel", filename="reports.xlsx")
