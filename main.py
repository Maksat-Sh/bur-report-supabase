import os
import ssl
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text, select
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# 🔐 SSL для Supabase
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": ssl_context},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ================== MODELS ==================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # dispatcher / driller


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    area: Mapped[str] = mapped_column(String(100))
    rig_number: Mapped[str] = mapped_column(String(50))
    meters: Mapped[int] = mapped_column(Integer)
    pogonometer: Mapped[str] = mapped_column(String(50))
    operations: Mapped[str] = mapped_column(String(200))
    responsible: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text)


# ================== APP ==================

app = FastAPI(title="Bur Report")


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ================== ROUTES ==================

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <h2>Bur Report</h2>
    <ul>
      <li><a href="/login">Вход диспетчера</a></li>
      <li><a href="/reports">Сводки буровиков</a></li>
    </ul>
    """


# ---------- LOGIN (БЕЗ ТОКЕНОВ) ----------

@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return """
    <h3>Вход диспетчера</h3>
    <form method="post">
        <input name="username" placeholder="Логин"/><br>
        <input name="password" type="password" placeholder="Пароль"/><br>
        <button type="submit">Войти</button>
    </form>
    """


@app.post("/login", response_class=HTMLResponse)
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.username == username,
            User.password == password,
            User.role == "dispatcher",
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        return "<h3>Неверный логин или пароль</h3>"

    return "<h3>Вы вошли как диспетчер ✅</h3><a href='/reports'>Смотреть сводки</a>"


# ---------- REPORTS ----------

@app.get("/reports", response_class=HTMLResponse)
async def reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    rows = result.scalars().all()

    html = "<h2>Сводки буровиков</h2><table border=1>"
    html += "<tr><th>Дата</th><th>Участок</th><th>Буровая</th><th>Метраж</th><th>Погонометр</th></tr>"

    for r in rows:
        html += f"""
        <tr>
            <td>{r.created_at}</td>
            <td>{r.area}</td>
            <td>{r.rig_number}</td>
            <td>{r.meters}</td>
            <td>{r.pogonometer}</td>
        </tr>
        """

    html += "</table>"
    return html


# ---------- DB CHECK ----------

@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(1))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "detail": str(e)}
