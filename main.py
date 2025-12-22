import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text, select
from datetime import datetime

# =========================
# DATABASE
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


# =========================
# MODELS
# =========================

class Dispatcher(Base):
    __tablename__ = "dispatchers"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(100))


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    section: Mapped[str] = mapped_column(String(100))
    rig_number: Mapped[str] = mapped_column(String(50))
    meters: Mapped[int] = mapped_column(Integer)
    pogonometer: Mapped[int] = mapped_column(Integer)
    operations: Mapped[str] = mapped_column(Text)
    responsible: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, nullable=True)


# =========================
# APP
# =========================

app = FastAPI()
templates = Jinja2Templates(directory="templates")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# =========================
# STARTUP
# =========================

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("🚀 Application started")


# =========================
# HEALTH CHECK
# =========================

@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(1))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "detail": str(e)}


# =========================
# LOGIN (DISPATCHER)
# =========================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dispatcher).where(
            Dispatcher.username == username,
            Dispatcher.password == password
        )
    )
    dispatcher = result.scalar_one_or_none()

    if not dispatcher:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    response = RedirectResponse("/dispatcher", status_code=302)
    response.set_cookie("dispatcher", username)
    return response


# =========================
# DISPATCHER PANEL
# =========================

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_panel(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    dispatcher = request.cookies.get("dispatcher")
    if not dispatcher:
        return RedirectResponse("/login")

    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    reports = result.scalars().all()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )


# =========================
# CREATE DISPATCHER (ONE TIME)
# =========================

@app.post("/create-dispatcher")
async def create_dispatcher(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    dispatcher = Dispatcher(username=username, password=password)
    db.add(dispatcher)
    await db.commit()
    return {"status": "created"}


# =========================
# DRILLER REPORT FORM (API)
# =========================

@app.post("/report")
async def submit_report(
    section: str = Form(...),
    rig_number: str = Form(...),
    meters: int = Form(...),
    pogonometer: int = Form(...),
    operations: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    report = Report(
        section=section,
        rig_number=rig_number,
        meters=meters,
        pogonometer=pogonometer,
        operations=operations,
        responsible=responsible,
        note=note,
    )
    db.add(report)
    await db.commit()
    return {"message": "Report submitted successfully"}


# =========================
# ROOT
# =========================

@app.get("/")
async def root():
    return RedirectResponse("/login")
