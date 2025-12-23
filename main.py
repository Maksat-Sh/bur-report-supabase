import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from passlib.context import CryptContext
from dotenv import load_dotenv

# -------------------------
# ENV
# -------------------------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SECRET = os.getenv("SESSION_SECRET", "super-secret")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# ❗ ВАЖНО: убираем sslmode из URL если вдруг есть
DATABASE_URL = DATABASE_URL.replace("?sslmode=require", "").replace("&sslmode=require", "")

# -------------------------
# DB
# -------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "ssl": True  # ✅ ВАЖНО для Supabase
    },
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# -------------------------
# SECURITY
# -------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

# -------------------------
# APP
# -------------------------
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# -------------------------
# AUTH HELPERS
# -------------------------
def require_login(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

# -------------------------
# ROUTES
# -------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

    return HTMLResponse("""
    <h2>Диспетчер</h2>
    <p>Вы вошли в систему</p>
    <a href="/logout">Выйти</a>
    """)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse("""
    <h2>Вход</h2>
    <form method="post">
        <input name="username" placeholder="Логин"><br>
        <input name="password" type="password" placeholder="Пароль"><br>
        <button type="submit">Войти</button>
    </form>
    """)

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    q = text("""
        SELECT username, password_hash
        FROM users
        WHERE username = :u
    """)
    result = await db.execute(q, {"u": username})
    user = result.fetchone()

    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse("<h3>Неверный логин или пароль</h3>", status_code=401)

    request.session["user"] = user.username
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return PlainTextResponse("DB OK")
