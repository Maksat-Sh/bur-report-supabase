import os
import hashlib
import hmac
import binascii
import asyncpg
import io
import pandas as pd

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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

# ================== PASSWORD ==================

def verify_password(password: str, stored_hash: str) -> bool:
    """
    pbkdf2_sha256$29000$salt_hex$hash_hex
    """
    try:
        _, iterations, salt_hex, hash_hex = stored_hash.split("$")
        salt = binascii.unhexlify(salt_hex)
        stored = binascii.unhexlify(hash_hex)

        new = hashlib.pbkdf2_hmac(
            ALGORITHM,
            password.encode(),
            salt,
            int(iterations),
            dklen=len(stored)
        )
        return hmac.compare_digest(new, stored)
    except Exception:
        return False

# ================== AUTH ==================

@app.get("/")
async def root(request: Request):
    role = request.session.get("role")
    if role == "dispatcher":
        return RedirectResponse("/dispatcher")
    if role == "bur":
        return RedirectResponse("/bur")
    return RedirectResponse("/login")

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
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, password_hash, role FROM users WHERE username=$1",
            username
        )

    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login", 302)

    request.session["user"] = user["username"]
    request.session["role"] = user["role"]

    return RedirectResponse("/", 302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ================== BUR ==================

@app.get("/bur", response_class=HTMLResponse)
async def bur_page(request: Request):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login")

    return """
    <h2>Сводка буровика</h2>
    <form method="post">
        Участок: <input name="area"><br><br>
        Буровая: <input name="rig"><br><br>
        Метраж: <input name="meters" type="number"><br><br>
        Погонометр: <input name="pogonometer"><br><br>
        Примечание:<br>
        <textarea name="note"></textarea><br><br>
        <button>Отправить</button>
    </form>
    <a href="/logout">Выйти</a>
    """

@app.post("/bur")
async def bur_submit(
    request: Request,
    area: str = Form(...),
    rig: str = Form(...),
    meters: int = Form(...),
    pogonometer: str = Form(...),
    note: str = Form("")
):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login")

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reports (username, area, rig, meters, pogonometer, note)
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
        request.session["user"], area, rig, meters, pogonometer, note)

    return RedirectResponse("/bur", 302)

# ================== DISPATCHER ==================

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at DESC")

    html = "<h1>Диспетчерская</h1><a href='/export'>Экспорт в Excel</a><br><br><table border=1>"
    html += "<tr><th>Дата</th><th>Буровик</th><th>Участок</th><th>Буровая</th><th>Метраж</th><th>Погонометр</th><th>Примечание</th></tr>"

    for r in rows:
        html += f"<tr><td>{r['created_at']}</td><td>{r['username']}</td><td>{r['area']}</td><td>{r['rig']}</td><td>{r['meters']}</td><td>{r['pogonometer']}</td><td>{r['note']}</td></tr>"

    html += "</table><br><a href='/logout'>Выйти</a>"
    return html

# ================== EXCEL ==================

@app.get("/export")
async def export_excel(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at")

    df = pd.DataFrame(rows)
    stream = io.BytesIO()
    df.to_excel(stream, index=False)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )

# ================== DB CHECK ==================

@app.get("/db-check")
async def db_check():
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
