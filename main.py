import os
import ssl
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Float, text

# =========================
# ENV
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
DISPATCHER_LOGIN = os.getenv("DISPATCHER_LOGIN", "dispatcher")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD", "1234")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# =========================
# SSL (обязательно для Supabase)
# =========================
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": ssl_context},
)

AsyncSessionLocal = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

Base = declarative_base()

# =========================
# MODELS
# =========================
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    area = Column(String)
    rig_number = Column(String)
    meters = Column(Float)
    pogonometer = Column(Float)
    note = Column(String)


# =========================
# APP
# =========================
app = FastAPI()


# =========================
# DB
# =========================
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database connected")


# =========================
# ROUTES
# =========================
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <h2>Bur Report</h2>
    <a href="/login">Диспетчер</a>
    """


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <form method="post">
        <input name="login" placeholder="Логин"><br>
        <input name="password" type="password" placeholder="Пароль"><br>
        <button>Войти</button>
    </form>
    """


@app.post("/login", response_class=HTMLResponse)
async def login(login: str = Form(...), password: str = Form(...)):
    if login == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        return "<h3>Успешный вход</h3><a href='/reports'>Сводки</a>"
    raise HTTPException(status_code=401, detail="Неверный логин или пароль")


@app.get("/reports")
async def reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM reports ORDER BY created_at DESC"))
    rows = result.fetchall()
    return rows


@app.post("/report")
async def create_report(
    area: str = Form(...),
    rig_number: str = Form(...),
    meters: float = Form(...),
    pogonometer: float = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    report = Report(
        area=area,
        rig_number=rig_number,
        meters=meters,
        pogonometer=pogonometer,
        note=note,
    )
    db.add(report)
    await db.commit()
    return {"message": "Report saved"}


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}
