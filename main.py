import os
import bcrypt
from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, DateTime, Text

# ----------------------------- CONFIG ---------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не найден в переменных окружения!")

# Убираем sslmode — asyncpg сам включает SSL на Render
if "sslmode" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split("?")[0]

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# ----------------------------- MODELS ---------------------------------

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # dispatcher, bur


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datetime: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    area: Mapped[str] = mapped_column(String(200))
    rig_number: Mapped[str] = mapped_column(String(200))
    depth: Mapped[str] = mapped_column(String(200))
    pogon: Mapped[str] = mapped_column(String(200))
    operation: Mapped[str] = mapped_column(String(200))
    responsible: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text)


# ----------------------------- INIT DB ---------------------------------


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(select(User))
        users = result.scalars().all()

        if not users:
            # Создаём диспетчера
            pwd = bcrypt.hashpw("1234".encode(), bcrypt.gensalt()).decode()
            session.add(User(username="dispatcher", password_hash=pwd, role="dispatcher"))

            # Создаём буровиков
            b1 = bcrypt.hashpw("123".encode(), bcrypt.gensalt()).decode()
            b2 = bcrypt.hashpw("123".encode(), bcrypt.gensalt()).decode()

            session.add(User(username="bur1", password_hash=b1, role="bur"))
            session.add(User(username="bur2", password_hash=b2, role="bur"))

            await session.commit()


# ----------------------------- APP ---------------------------------

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def on_start():
    await init_db()


# ----------------------------- AUTH ---------------------------------

async def get_current_user(request: Request):
    username = request.cookies.get("user")
    if not username:
        return None

    async with SessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    async with SessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            return RedirectResponse("/?error=1", status_code=302)

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return RedirectResponse("/?error=1", status_code=302)

        # redirect по ролям
        resp = RedirectResponse(
            "/dispatcher" if user.role == "dispatcher" else "/burform", status_code=302
        )
        resp.set_cookie("user", user.username)
        return resp


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ------------------------- DISPATCHER PANEL ---------------------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request, user=Depends(get_current_user)):
    if not user or user.role != "dispatcher":
        return RedirectResponse("/", status_code=302)

    async with SessionLocal() as session:
        from sqlalchemy import select
        reports = (await session.execute(select(Report))).scalars().all()
        users = (await session.execute(select(User))).scalars().all()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports, "users": users}
    )


# Create new user by dispatcher
@app.post("/create_user")
async def create_user(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        role: str = Form(...)
):
    async with SessionLocal() as session:
        pwd = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        session.add(User(username=username, password_hash=pwd, role=role))
        await session.commit()

    return RedirectResponse("/dispatcher", status_code=302)


# ------------------------------- BUR FORM ------------------------------

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request, user=Depends(get_current_user)):
    if not user or user.role != "bur":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/burform")
async def submit_form(
        area: str = Form(...),
        rig_number: str = Form(...),
        depth: str = Form(...),
        pogon: str = Form(...),
        operation: str = Form(...),
        responsible: str = Form(...),
        note: str = Form("")
):
    async with SessionLocal() as session:
        report = Report(
            area=area,
            rig_number=rig_number,
            depth=depth,
            pogon=pogon,
            operation=operation,
            responsible=responsible,
            note=note
        )
        session.add(report)
        await session.commit()

    return RedirectResponse("/burform?ok=1", status_code=302)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("user")
    return resp
