import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text, select
from datetime import datetime

# ======================
# НАСТРОЙКИ
# ======================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@host/dbname?ssl=require"
)

DISPATCHER_LOGIN = os.getenv("DISPATCHER_LOGIN", "dispatcher")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD", "1234")

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

# ======================
# DATABASE
# ======================

engine = create_async_engine(
    DATABASE_URL,
    echo=True,          # важно для отладки
    pool_pre_ping=True
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(50))


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site: Mapped[str] = mapped_column(String(100))
    rig_number: Mapped[str] = mapped_column(String(50))
    meters: Mapped[int] = mapped_column(Integer)
    pogonometer: Mapped[str] = mapped_column(String(50))
    operations: Mapped[str] = mapped_column(Text)
    responsible: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ======================
# APP
# ======================

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")


# ======================
# STARTUP (ТОЛЬКО СОЗДАНИЕ ТАБЛИЦ)
# ======================

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database ready")


# ======================
# AUTH
# ======================

def require_dispatcher(request: Request):
    if not request.session.get("dispatcher"):
        raise HTTPException(status_code=401)
    return True


# ======================
# LOGIN / LOGOUT
# ======================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        request.session["dispatcher"] = True
        return RedirectResponse("/dispatcher", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"},
        status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ======================
# DISPATCHER
# ======================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("dispatcher"):
        return RedirectResponse("/dispatcher")
    return RedirectResponse("/login")


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_dispatcher)
):
    reports = (await db.execute(select(Report).order_by(Report.created_at.desc()))).scalars().all()
    users = (await db.execute(select(User))).scalars().all()

    return templates.TemplateResponse(
        "dispatcher.html",
        {
            "request": request,
            "reports": reports,
            "users": users
        }
    )


# ======================
# CREATE USER (БУРОВИК)
# ======================

@app.post("/create-user")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_dispatcher)
):
    try:
        user = User(username=username, password=password)
        db.add(user)
        await db.commit()
        return RedirectResponse("/dispatcher", status_code=302)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# REPORT FROM DRILLER
# ======================

@app.post("/submit-report")
async def submit_report(
    site: str = Form(...),
    rig_number: str = Form(...),
    meters: int = Form(...),
    pogonometer: str = Form(...),
    operations: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    report = Report(
        site=site,
        rig_number=rig_number,
        meters=meters,
        pogonometer=pogonometer,
        operations=operations,
        responsible=responsible,
        note=note
    )
    db.add(report)
    await db.commit()
    return {"status": "ok"}
