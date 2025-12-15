import os
import ssl
from datetime import datetime

from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import Column, Integer, String, DateTime, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

from passlib.context import CryptContext
from dotenv import load_dotenv

# ======================
# ENV
# ======================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

DISPATCHER_USERNAME = os.getenv("DISPATCHER_USERNAME")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD")

# ======================
# SSL ДЛЯ ASYNCPG (ВАЖНО)
# ======================
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": ssl_context}
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ======================
# MODELS
# ======================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="dispatcher")


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    area = Column(String)
    rig_number = Column(String)
    meters = Column(String)
    pogonometer = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# ======================
# APP
# ======================
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ======================
# DB
# ======================
async def get_db():
    async with async_session() as session:
        yield session

# ======================
# STARTUP
# ======================
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # создаём диспетчера автоматически
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == DISPATCHER_USERNAME))
        user = result.scalar_one_or_none()

        if not user:
            db.add(
                User(
                    username=DISPATCHER_USERNAME,
                    password_hash=pwd_context.hash(DISPATCHER_PASSWORD),
                    role="dispatcher"
                )
            )
            await db.commit()

# ======================
# AUTH
# ======================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    response = RedirectResponse("/dispatcher", status_code=302)
    response.set_cookie("user", user.username)
    return response

# ======================
# DISPATCHER
# ======================
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not request.cookies.get("user"):
        return RedirectResponse("/login")
    return templates.TemplateResponse("dispatcher.html", {"request": request})

# ======================
# CREATE USER (ДИСПЕТЧЕР)
# ======================
@app.post("/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Пользователь уже существует")

    db.add(
        User(
            username=username,
            password_hash=pwd_context.hash(password),
            role="dispatcher"
        )
    )
    await db.commit()
    return RedirectResponse("/dispatcher", status_code=302)
