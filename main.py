import os
from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_123"
)

# =======================
# MODELS
# =======================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_dispatcher = Column(Boolean, default=False)

# =======================
# STARTUP
# =======================

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# =======================
# HELPERS
# =======================

def get_current_user(request: Request):
    return request.session.get("user")

def require_dispatcher(request: Request):
    user = get_current_user(request)
    if not user or not user.get("is_dispatcher"):
        return RedirectResponse("/login", status_code=302)
    return user

# =======================
# AUTH
# =======================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    async with AsyncSessionLocal() as db:
        q = select(User).where(User.username == username)
        result = await db.execute(q)
        user = result.scalar_one_or_none()

        if not user or user.password != password:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Неверный логин или пароль"},
                status_code=401
            )

        request.session["user"] = {
            "id": user.id,
            "username": user.username,
            "is_dispatcher": user.is_dispatcher
        }

        return RedirectResponse("/dispatcher", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# =======================
# DISPATCHER
# =======================

@app.get("/")
async def root():
    return RedirectResponse("/dispatcher", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    user = require_dispatcher(request)
    if isinstance(user, RedirectResponse):
        return user

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": user}
    )

# =======================
# USERS MANAGEMENT
# =======================

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = require_dispatcher(request)
    if isinstance(user, RedirectResponse):
        return user

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

    return templates.TemplateResponse(
        "users.html",
        {"request": request, "users": users}
    )

@app.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_dispatcher: bool = Form(False)
):
    user = require_dispatcher(request)
    if isinstance(user, RedirectResponse):
        return user

    async with AsyncSessionLocal() as db:
        new_user = User(
            username=username,
            password=password,
            is_dispatcher=is_dispatcher
        )
        db.add(new_user)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

    return RedirectResponse("/users", status_code=302)
