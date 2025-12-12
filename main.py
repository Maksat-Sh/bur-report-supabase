import os
import ssl
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, func, select
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# -------------------------------
# Настройки
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set!")

# === SSL FIX — обязательный для Render ===
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": ssl_ctx},     # ← ключевая строка!
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

Base = declarative_base()

# -------------------------------
# Модели
# -------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)


# -------------------------------
# Приложение
# -------------------------------
app = FastAPI()

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


async def get_db():
    async with SessionLocal() as session:
        yield session


# -------------------------------
# Главная → редирект на /login
# -------------------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")


# -------------------------------
# Логин (страница)
# -------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# -------------------------------
# Логин (POST)
# -------------------------------
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    query = select(User).where(User.username == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or user.password != form_data.password:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")

    return {"access_token": "ok", "token_type": "bearer"}


# -------------------------------
# Создание таблиц при старте
# -------------------------------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
