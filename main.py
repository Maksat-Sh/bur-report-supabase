import os
import ssl
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, select
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

# ---------- SSL для Render ----------
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": ssl_context},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# ---------- DB ----------
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="dispatcher")


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- FastAPI ----------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


async def get_db():
    async with SessionLocal() as session:
        yield session


# ---------- STARTUP ----------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # создать диспетчера, если нет
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "dispatcher"))
        user = result.scalar_one_or_none()
        if not user:
            db.add(
                User(
                    username="dispatcher",
                    password_hash=pwd_context.hash("1234"),
                    role="dispatcher",
                )
            )
            await db.commit()


# ---------- PAGES ----------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    with open("templates/login.html", encoding="utf-8") as f:
        return f.read()


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    return RedirectResponse("/dispatcher", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page():
    with open("templates/dispatcher.html", encoding="utf-8") as f:
        return f.read()
