import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, select
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv

# =======================
# ENV
# =======================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# =======================
# DB
# =======================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# =======================
# MODELS
# =======================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # dispatcher / bur

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    site = Column(String)
    rig_number = Column(String)
    meters = Column(Integer)
    pogonometer = Column(Integer)
    note = Column(Text)

# =======================
# AUTH
# =======================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)

# =======================
# APP
# =======================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# =======================
# STARTUP (БЕЗ ПРОВЕРКИ БД)
# =======================
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# =======================
# ROUTES
# =======================
@app.get("/", response_class=HTMLResponse)
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

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неправильные логин или пароль"}
        )

    if user.role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})

# =======================
# CREATE USER (ТОЛЬКО ДИСПЕТЧЕР)
# =======================
@app.post("/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role
    )
    db.add(user)
    await db.commit()
    return RedirectResponse("/dispatcher", status_code=302)
