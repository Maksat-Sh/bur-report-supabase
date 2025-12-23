import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy import text
from dotenv import load_dotenv
from passlib.context import CryptContext

# ======================
# ENV
# ======================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

# ======================
# DB
# ======================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": True  # ← ВОТ ЗДЕСЬ, А НЕ sslmode
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)

# ======================
# APP
# ======================
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ======================
# HELPERS
# ======================
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# ======================
# ROUTES
# ======================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return HTMLResponse(f"""
        <h2>Вы вошли как: {user["username"]}</h2>
        <p>Роль: {user["role"]}</p>
        <a href="/logout">Выйти</a>
    """)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    async with AsyncSessionLocal() as db:
        q = text("""
            SELECT username, password_hash, role
            FROM users
            WHERE username = :u
        """)
        result = await db.execute(q, {"u": username})
        user = result.fetchone()

        if not user:
            return HTMLResponse("Пользователь не найден", status_code=401)

        if not pwd_context.verify(password, user.password_hash):
            return HTMLResponse("Неверный пароль", status_code=401)

        request.session["user"] = {
            "username": user.username,
            "role": user.role,
        }

        return RedirectResponse("/", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/db-check")
async def db_check():
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
    return PlainTextResponse("DB OK")
