import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- HELPERS ----------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def require_login(request: Request, role: str | None = None):
    user = request.session.get("user")
    if not user:
        return None
    if role and user["role"] != role:
        return None
    return user


# ---------- ROUTES ----------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/driller", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    with open("templates/login.html", encoding="utf-8") as f:
        return f.read()


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    async with SessionLocal() as db:
        q = text("""
            SELECT id, username, password_hash, role
            FROM users
            WHERE username = :u
        """)
        res = await db.execute(q, {"u": username})
        user = res.mappings().first()

    if not user or not verify_password(password, user["password_hash"]):
        return HTMLResponse("Неверный логин или пароль", status_code=401)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"]
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    return RedirectResponse("/driller", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    user = require_login(request, "dispatcher")
    if not user:
        return RedirectResponse("/login", status_code=302)

    with open("templates/dispatcher.html", encoding="utf-8") as f:
        return f.read()


@app.get("/driller", response_class=HTMLResponse)
async def driller_page(request: Request):
    user = require_login(request, "driller")
    if not user:
        return RedirectResponse("/login", status_code=302)

    with open("templates/driller.html", encoding="utf-8") as f:
        return f.read()


@app.get("/db-check")
async def db_check():
    async with SessionLocal() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "ok"}
