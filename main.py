import os
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select
from passlib.context import CryptContext
from dotenv import load_dotenv

# ---------- ENV ----------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

# ---------- DB ----------
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={
        "ssl": "require"   # 🔥 ВАЖНО для Render
    }
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# ---------- MODELS ----------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_dispatcher = Column(Boolean, default=False)

# ---------- SECURITY ----------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)

# ---------- APP ----------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- DB INIT ----------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # создаём диспетчера, если его нет
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == "dispatcher")
        )
        dispatcher = result.scalar_one_or_none()

        if not dispatcher:
            dispatcher = User(
                username="dispatcher",
                password_hash=hash_password("1234"),
                is_dispatcher=True
            )
            db.add(dispatcher)
            await db.commit()

# ---------- DEP ----------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ---------- ROUTES ----------
@app.get("/", response_class=HTMLResponse)
async def login_page():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_form():
    with open("templates/login.html", encoding="utf-8") as f:
        return f.read()

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    if user.is_dispatcher:
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page():
    with open("templates/dispatcher.html", encoding="utf-8") as f:
        return f.read()

@app.post("/dispatcher/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(User.username == username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    user = User(
        username=username,
        password_hash=hash_password(password),
        is_dispatcher=False
    )
    db.add(user)
    await db.commit()

    return RedirectResponse("/dispatcher", status_code=302)

@app.get("/burform", response_class=HTMLResponse)
async def burform():
    with open("templates/burform.html", encoding="utf-8") as f:
        return f.read()
