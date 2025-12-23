import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
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

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

# ---------- Sessions ----------
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
)

# ---------- Static ----------
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- DB ----------
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},  # ВАЖНО для Supabase
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ---------- Utils ----------
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def hash_password(password):
    return pwd_context.hash(password)


def require_login(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)


# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

    role = request.session["user"]["role"]
    if role == "dispatcher":
        return HTMLResponse("<h1>Диспетчер</h1><a href='/logout'>Выйти</a>")
    return HTMLResponse("<h1>Буровик</h1><a href='/logout'>Выйти</a>")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(open("templates/login.html", encoding="utf-8").read())


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    query = text("""
        SELECT id, username, role, password_hash
        FROM users
        WHERE username = :u
    """)
    result = await db.execute(query, {"u": username})
    user = result.fetchone()

    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse("Неверный логин или пароль", status_code=401)

    request.session["user"] = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }

    return RedirectResponse("/", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("select 1"))
    return {"status": "ok"}
