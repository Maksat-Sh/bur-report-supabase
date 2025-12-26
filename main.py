import os
import asyncpg
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

# ================== CONFIG ==================

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

pool: asyncpg.Pool | None = None

# ================== DB ==================

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=3,   # 🔴 КРИТИЧНО для Render Free
        command_timeout=60
    )

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

# ================== AUTH ==================

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

# ================== ROUTES ==================

@app.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return """
    <h2>Вход диспетчера</h2>
    <form method="post">
        <input name="username" placeholder="Логин"><br><br>
        <input name="password" type="password" placeholder="Пароль"><br><br>
        <button>Войти</button>
    </form>
    """

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT username, password_hash, role
            FROM users
            WHERE username = $1
            """,
            username
        )

    if not user:
        return RedirectResponse("/login", status_code=302)

    if not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login", status_code=302)

    request.session["user"] = user["username"]
    request.session["role"] = user["role"]

    return RedirectResponse("/dispatcher", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    return """
    <h1>Диспетчерская</h1>
    <p>Вы успешно вошли</p>
    <a href="/logout">Выйти</a>
    """

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ================== DEBUG ==================

@app.get("/db-check")
async def db_check():
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
