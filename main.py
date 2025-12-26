import os
import hashlib
import hmac
import binascii
import asyncpg
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# ================== CONFIG ==================

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

ALGORITHM = "sha256"

# ================== APP ==================

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

pool: asyncpg.Pool | None = None

# ================== STARTUP ==================

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=3
    )

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

# ================== PASSWORD CHECK ==================

def verify_password(password: str, stored_hash: str) -> bool:
    """
    stored_hash:
    pbkdf2_sha256$29000$salt_hex$hash_hex
    """
    try:
        algo, iterations, salt_hex, hash_hex = stored_hash.split("$")
        iterations = int(iterations)

        salt = binascii.unhexlify(salt_hex)
        stored = binascii.unhexlify(hash_hex)

        new_hash = hashlib.pbkdf2_hmac(
            ALGORITHM,
            password.encode(),
            salt,
            iterations,
            dklen=len(stored)
        )

        return hmac.compare_digest(new_hash, stored)
    except Exception:
        return False

# ================== ROUTES ==================

@app.get("/")
async def root(request: Request):
    if request.session.get("role") == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    if request.session.get("role") == "bur":
        return RedirectResponse("/bur", status_code=302)
    return RedirectResponse("/login", status_code=302)

# ---------- LOGIN ----------

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
            """
            SELECT id, username, role, password_hash
            FROM users
            WHERE username=$1
            """,
            username
        )

    if not user:
        return RedirectResponse("/login", status_code=302)

    if not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login", status_code=302)

    request.session["user_id"] = user["id"]
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    return RedirectResponse("/bur", status_code=302)

# ---------- DISPATCHER ----------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    return """
    <h1>Диспетчерская</h1>
    <ul>
        <li><a href="/reports">Сводки</a></li>
        <li><a href="/logout">Выйти</a></li>
    </ul>
    """

# ---------- BUR FORM ----------

@app.get("/bur", response_class=HTMLResponse)
async def bur_form(request: Request):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login", status_code=302)

    return """
    <h2>Смена буровика</h2>
    <form method="post" action="/bur/report">
        Участок: <input name="area"><br><br>
        № буровой: <input name="rig"><br><br>
        Метраж: <input name="meters" type="number"><br><br>
        Погонометр: <input name="pogonometr"><br><br>
        Примечание:<br>
        <textarea name="note"></textarea><br><br>
        <button>Отправить</button>
    </form>
    <br>
    <a href="/logout">Выйти</a>
    """

@app.post("/bur/report")
async def bur_report(
    request: Request,
    area: str = Form(...),
    rig: str = Form(...),
    meters: int = Form(...),
    pogonometr: str = Form(...),
    note: str = Form("")
):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login", status_code=302)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reports
            (created_at, area, rig, meters, pogonometr, note, user_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            datetime.utcnow(),
            area,
            rig,
            meters,
            pogonometr,
            note,
            request.session["user_id"]
        )

    return RedirectResponse("/bur", status_code=302)

# ---------- LOGOUT ----------

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ---------- DB CHECK ----------

@app.get("/db-check")
async def db_check():
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
