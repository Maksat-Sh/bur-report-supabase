import os
from datetime import datetime

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, select

DATABASE_URL = os.getenv("DATABASE_URL")
DISPATCHER_LOGIN = os.getenv("DISPATCHER_LOGIN", "dispatcher")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD", "1234")

# ---------- DB ----------

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    site: Mapped[str] = mapped_column(String)
    rig_number: Mapped[str] = mapped_column(String)
    meters: Mapped[int] = mapped_column(Integer)
    pogonometr: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String)
    responsible: Mapped[str] = mapped_column(String)
    comment: Mapped[str] = mapped_column(String, nullable=True)

# ---------- APP ----------

app = FastAPI()
templates = Jinja2Templates(directory="templates")

async def get_db():
    async with SessionLocal() as session:
        yield session

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("🚀 Application started")

# ---------- AUTH (БЕЗ ТОКЕНОВ) ----------

def check_dispatcher(login: str = Form(...), password: str = Form(...)):
    if login != DISPATCHER_LOGIN or password != DISPATCHER_PASSWORD:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

# ---------- ROUTES ----------

@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_action(
    login: str = Form(...),
    password: str = Form(...),
):
    if login == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse("❌ Неверный логин или пароль", status_code=401)

@app.post("/submit-report")
async def submit_report(
    site: str = Form(...),
    rig_number: str = Form(...),
    meters: int = Form(...),
    pogonometr: int = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    report = Report(
        site=site,
        rig_number=rig_number,
        meters=meters,
        pogonometr=pogonometr,
        operation=operation,
        responsible=responsible,
        comment=comment,
    )
    db.add(report)
    await db.commit()
    return {"message": "Сводка принята"}

@app.get("/reports")
async def get_reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    reports = result.scalars().all()
    return reports

@app.get("/db-check")
async def db_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "detail": str(e)}
