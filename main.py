# main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime
import io
from openpyxl import Workbook
import hashlib
from passlib.context import CryptContext
import typing

# load .env
load_dotenv()

# app
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecretkey"))

# templates + static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# DB config - установите DATABASE_URL в .env, пример:
# postgresql://postgres:YOUR_PASSWORD@db.your.supabase.co:5432/postgres
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("SUPABASE_PG_URL")
if not DATABASE_URL:
    print("WARNING: DATABASE_URL not set. App will not be able to use PostgreSQL.")

# Supabase REST (опционально) - оставлено на случай, если захотите
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# password contexts (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# global pool
pg_pool: typing.Optional[asyncpg.pool.Pool] = None

# ---------------------------
# helpers
# ---------------------------
def check_password_from_db(plain_password: str, stored_hash: str) -> bool:
    """
    Support bcrypt and legacy SHA256 hex string.
    If stored starts with $2 -> bcrypt (passlib)
    If length 64 hex -> SHA256 hex compare
    Otherwise try passlib then sha256 fallback.
    """
    if not stored_hash:
        return False
    s = stored_hash.strip()
    # bcrypt
    if s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$"):
        try:
            return pwd_context.verify(plain_password, s)
        except Exception:
            return False
    # sha256 hex
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        return hashlib.sha256(plain_password.encode()).hexdigest() == s.lower()
    # fallback
    try:
        if pwd_context.verify(plain_password, s):
            return True
    except Exception:
        pass
    return hashlib.sha256(plain_password.encode()).hexdigest() == s.lower()

def get_current_user(request: Request):
    return request.session.get("user")

# ---------------------------
# startup / shutdown
# ---------------------------
@app.on_event("startup")
async def startup():
    global pg_pool
    if DATABASE_URL:
        try:
            pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            # ensure tables exist
            async with pg_pool.acquire() as conn:
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT,
                    password_hash TEXT,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    date TEXT,
                    time TEXT,
                    section TEXT,
                    rig_number TEXT,
                    meterage TEXT,
                    pogonometr TEXT,
                    operation_type TEXT,
                    operator_name TEXT,
                    note TEXT
                );
                """)
                # create default users if none
                rows = await conn.fetchval("SELECT count(*) FROM users;")
                if rows == 0:
                    print("Users table empty — creating default accounts")
                    # default: store sha256 for immediate login (dispatcher:1234, bur1:123)
                    dispatcher_pw = hashlib.sha256("1234".encode()).hexdigest()
                    bur1_pw = hashlib.sha256("123".encode()).hexdigest()
                    await conn.execute(
                        "INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES ($1,$2,$3,$4,$5)",
                        "dispatcher", "Диспетчер", dispatcher_pw, "dispatcher", datetime.utcnow()
                    )
                    await conn.execute(
                        "INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES ($1,$2,$3,$4,$5)",
                        "bur1", "Буровик 1", bur1_pw, "driller", datetime.utcnow()
                    )
        except Exception as e:
            print("Postgres connect/create error:", e)
            pg_pool = None
    else:
        print("No DATABASE_URL - DB disabled.")

@app.on_event("shutdown")
async def shutdown():
    global pg_pool
    if pg_pool:
        await pg_pool.close()

# ---------------------------
# DB helpers (Postgres)
# ---------------------------
async def db_fetch_users_by_username(username: str):
    if not pg_pool:
        return []
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users WHERE username = $1", username)
        return [dict(r) for r in rows]

async def db_fetch_reports(params: str = None):
    if not pg_pool:
        return []
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at DESC")
        return [dict(r) for r in rows]

async def db_insert_report(payload: dict):
    if not pg_pool:
        raise RuntimeError("DB not available")
    async with pg_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reports (date, time, section, rig_number, meterage, pogonometr, operation_type, operator_name, note)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """, payload.get("date"), payload.get("time"), payload.get("section"),
           payload.get("rig_number"), payload.get("meterage"), payload.get("pogonometr"),
           payload.get("operation_type"), payload.get("operator_name"), payload.get("note"))

async def db_create_user(payload: dict):
    if not pg_pool:
        raise RuntimeError("DB not available")
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO users (username, full_name, password_hash, role, created_at)
            VALUES ($1,$2,$3,$4,$5) RETURNING *
        """, payload.get("username"), payload.get("full_name"), payload.get("password_hash"),
           payload.get("role"), datetime.utcnow())
        return dict(row)

# ---------------------------
# Routes
# ---------------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # prefer DB users (Postgres)
    users = []
    try:
        users = await db_fetch_users_by_username(username) if pg_pool else []
    except Exception as e:
        print("Supabase/Postgres read error during login, falling back to none:", e)
        users = []

    if not users:
        # no user found -> invalid login
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    user = users[0]
    if not check_password_from_db(password, user.get("password_hash", "")):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    # successful -> put user minimal info in session
    request.session["user"] = {"id": user.get("id"), "username": user.get("username"), "full_name": user.get("full_name"), "role": user.get("role")}

    if user.get("role") == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# bur form (driller)
@app.get("/burform", response_class=HTMLResponse)
async def bur_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    # pass user so template can show name
    return templates.TemplateResponse("burform.html", {"request": request, "user": user})

@app.post("/submit_report")
async def submit_report(
        request: Request,
        date: str = Form(None),
        time: str = Form(None),
        section: str = Form(None),
        rig_number: str = Form(None),
        meterage: str = Form(None),
        pogon: str = Form(None),
        operation_type: str = Form(None),
        operator_name: str = Form(None),
        note: str = Form(None),
        # support alternate form names (from your burform.html)
        area: str = Form(None),
        rig: str = Form(None),
        meter: str = Form(None),
        operation: str = Form(None),
        person: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    # accept both name variants
    section = section or area
    rig_number = rig_number or rig
    meterage = meterage or meter
    operation_type = operation_type or operation
    operator_name = operator_name or person or user.get("username")

    payload = {
        "date": date or datetime.utcnow().date().isoformat(),
        "time": time or datetime.utcnow().time().strftime("%H:%M:%S"),
        "section": section or "",
        "rig_number": rig_number or "",
        "meterage": meterage or "",
        "pogonometr": pogon or "",
        "operation_type": operation_type or "",
        "operator_name": operator_name or "",
        "note": note or ""
    }

    try:
        await db_insert_report(payload)
    except Exception as e:
        print("db_insert_report error:", e)
        return {"error": str(e)}

    return RedirectResponse("/burform", status_code=302)

# dispatcher page
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    reports = []
    try:
        reports = await db_fetch_reports()
    except Exception as e:
        print("dispatcher_page db error:", e)
        reports = []

    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports})

# users page (dispatcher)
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    # fetch all users
    if not pg_pool:
        users = []
    else:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, username, full_name, role, created_at FROM users ORDER BY id")
            users = [dict(r) for r in rows]
    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": users})

# create user (dispatcher)
@app.post("/create_user")
async def create_user(
        request: Request,
        username: str = Form(...),
        full_name: str = Form(""),
        password: str = Form(...),
        role: str = Form("driller")
):
    admin = get_current_user(request)
    if not admin or admin.get("role") != "dispatcher":
        return RedirectResponse("/login")

    # hash password with bcrypt for new users
    password_hash = pwd_context.hash(password)
    payload = {"username": username, "full_name": full_name, "password_hash": password_hash, "role": role}
    try:
        created = await db_create_user(payload)
    except Exception as e:
        return templates.TemplateResponse("users.html", {"request": request, "user": admin, "error": str(e), "users": []})
    return RedirectResponse("/users", status_code=303)

# export excel
@app.get("/export_excel")
async def export_excel(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    reports = []
    try:
        reports = await db_fetch_reports()
    except Exception as e:
        print("export_excel error:", e)

    wb = Workbook()
    ws = wb.active
    ws.title = "reports"
    ws.append(["ID", "Дата UTC", "Участок", "Номер агрегата", "Метраж", "Погонометр", "Операция", "Автор", "Примечание"])
    for r in reports:
        ws.append([
            r.get("id"),
            r.get("created_at"),
            r.get("section"),
            r.get("rig_number"),
            r.get("meterage"),
            r.get("pogonometr"),
            r.get("operation_type"),
            r.get("operator_name"),
            r.get("note")
        ])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# simple healthcheck
@app.get("/ping")
def ping():
    return {"status": "ok"}
