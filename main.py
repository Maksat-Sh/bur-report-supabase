import os
import hashlib
import binascii
import asyncpg

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

pool: asyncpg.Pool | None = None


# ---------- PASSWORD UTILS ----------

def verify_password(password: str, stored: str) -> bool:
    """
    stored format:
    pbkdf2$iterations$salt_hex$hash_hex
    """
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        salt = binascii.unhexlify(salt_hex)
        iterations = int(iterations)

        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            iterations,
            dklen=32
        )
        return binascii.hexlify(dk).decode() == hash_hex
    except Exception:
        return False


# ---------- LIFECYCLE ----------

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=2,   # КРИТИЧНО для Supabase Free
        ssl="require"
    )


@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


# ---------- ROUTES ----------

@app.get("/db-check")
async def db_check():
    async with pool.acquire() as conn:
        await conn.execute("select 1")
    return {"status": "ok"}


@app.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", 302)
    return RedirectResponse("/login", 302)


@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return """
    <h2>Вход</h2>
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
            "select username, password_hash, role from users where username=$1",
            username
        )

    if not user:
        return RedirectResponse("/login", 302)

    if not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login", 302)

    request.session["user"] = user["username"]
    request.session["role"] = user["role"]

    return RedirectResponse("/dispatcher", 302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", 302)

    return """
    <h1>Диспетчерская</h1>
    <p>Вы успешно вошли</p>
    <a href="/logout">Выйти</a>
    """


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)
