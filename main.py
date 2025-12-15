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

# --------------------
# ENV
# --------------------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

# --------------------
# APP
# --------------------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --------------------
# DB + SSL (ВАЖНО)
# --------------------
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": ssl_context
    }
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# --------------------
# MODELS
# --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="dispatcher")
    created_at = Column(DateTime, default=datetime.utcnow)


# --------------------
# PASSWORDS
# --------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hash: str):
    return pwd_context.verify(password, hash)


# --------------------
# DB DEP
# --------------------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# --------------------
# STARTUP
# --------------------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # создать диспетчера если нет
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == "dispatcher")
        )
        user = result.scalar_one_or_none()
        if not user:
            db.add(
                User(
                    username="dispatcher",
                    password_hash=hash_password("1234"),
                    role="dispatcher"
                )
            )
            await db.commit()


# --------------------
# ROUTES
# --------------------
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
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
            status_code=401
        )

    response = RedirectResponse("/dispatcher", status_code=302)
    response.set_cookie("user", user.username, httponly=True)
    return response


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    user = request.cookies.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/")
async def root():
    return RedirectResponse("/login")
