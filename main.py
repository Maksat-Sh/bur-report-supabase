import os
import ssl

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from passlib.context import CryptContext
from dotenv import load_dotenv

# ========================
# ENV
# ========================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

# ========================
# SSL for Supabase Pooler
# ========================
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# ========================
# DATABASE
# ========================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": ssl_context
    }
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ========================
# SECURITY
# ========================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

# ========================
# APP
# ========================
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ========================
# AUTH HELPERS
# ========================
def require_login(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

# ========================
# ROUTES
# ========================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

    return HTMLResponse("""
    <h2>Диспетчер</h2>
    <p>Вы вошли в систему</p>
    <a href="/logout">Выйти</a>
    """)

# ------------------------
# LOGIN
# ------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(open("templates/login.html", encoding="utf-8").read())

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    q = text("""
        SELECT username, password_hash, role
        FROM users
        WHERE username = :u
    """)
    result = await db.execute(q, {"u": username})
    user = result.mappings().first()

    if not user or not verify_password(password, user["password_hash"]):
        return HTMLResponse(
            "<h3>Неверный логин или пароль</h3><a href='/login'>Назад</a>",
            status_code=401
        )

    request.session["user"] = {
        "username": user["username"],
        "role": user["role"]
    }

    return RedirectResponse("/", status_code=302)

# ------------------------
# LOGOUT
# ------------------------
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ------------------------
# DB CHECK
# ------------------------
@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
