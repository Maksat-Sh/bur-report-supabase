import os
import hashlib
import hmac
import binascii
import asyncpg
from io import BytesIO

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from openpyxl import Workbook

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

ITERATIONS = 29000
ALGORITHM = "sha256"

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="templates")

pool: asyncpg.Pool | None = None


@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)


@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


# ====== ХЭШ ======

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored_hash.split("$")
        iterations = int(iterations)
        salt = binascii.unhexlify(salt_hex)
        stored = binascii.unhexlify(hash_hex)

        new = hashlib.pbkdf2_hmac(
            ALGORITHM,
            password.encode(),
            salt,
            iterations,
            dklen=len(stored)
        )
        return hmac.compare_digest(new, stored)
    except Exception:
        return False


# ====== AUTH ======

@app.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", 302)
    return RedirectResponse("/login", 302)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request,
                username: str = Form(...),
                password: str = Form(...)):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE username=$1", username
        )

    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login", 302)

    request.session["user"] = user["username"]
    request.session["role"] = user["role"]

    return RedirectResponse("/dispatcher", 302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)


# ====== DRILLER ======

@app.get("/driller", response_class=HTMLResponse)
async def driller_form(request: Request):
    return templates.TemplateResponse("driller.html", {"request": request})


@app.post("/driller")
async def submit_report(
    section: str = Form(...),
    rig_number: str = Form(...),
    meters: float = Form(...),
    pogonometr: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form("")
):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reports
            (section, rig_number, meters, pogonometr, operation, responsible, note, driller)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        """, section, rig_number, meters, pogonometr, operation, responsible, note, responsible)

    return {"message": "ok"}


# ====== DISPATCHER ======

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", 302)

    async with pool.acquire() as conn:
        reports = await conn.fetch(
            "SELECT * FROM reports ORDER BY created_at DESC"
        )

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )


# ====== EXCEL ======

@app.get("/export")
async def export_excel(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", 302)

    wb = Workbook()
    ws = wb.active
    ws.append([
        "Дата",
        "Участок",
        "Буровая",
        "Метраж",
        "Погонометр",
        "Операция",
        "Ответственный",
        "Примечание"
    ])

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at")

    for r in rows:
        ws.append([
            r["created_at"],
            r["section"],
            r["rig_number"],
            r["meters"],
            r["pogonometr"],
            r["operation"],
            r["responsible"],
            r["note"]
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )


@app.get("/db-check")
async def db_check():
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
