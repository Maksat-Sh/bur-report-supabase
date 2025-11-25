# main.py — Supabase REST + fallback SQLite, готовый для Render
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime
import io
from openpyxl import Workbook
import hashlib
from passlib.context import CryptContext
import typing
import sqlite3
import traceback

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecretkey"))

# templates + static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Supabase REST config (from env)
SUPABASE_URL = os.getenv("SUPABASE_URL")  # e.g. https://xxxx.supabase.co
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # service_role recommended for server
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# password contexts
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# sqlite fallback DB file
SQLITE_DB = os.getenv("SQLITE_DB", "data.db")
USE_SQLITE = False  # set to True if we fall back

# -----------------------
# SQLite helpers (fallback)
# -----------------------
def sqlite_connect():
    conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite():
    conn = sqlite_connect()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        full_name TEXT,
        password_hash TEXT,
        role TEXT,
        created_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        time TEXT,
        section TEXT,
        rig_number TEXT,
        meterage TEXT,
        pogonometr TEXT,
        operation_type TEXT,
        operator_name TEXT,
        note TEXT,
        created_at TEXT
    );
    """)
    conn.commit()

    # create default users if none
    cur.execute("SELECT COUNT(*) AS c FROM users")
    c = cur.fetchone()["c"]
    if c == 0:
        print("Users table empty — creating default accounts in SQLite")
        dispatcher_pw = hashlib.sha256("1234".encode()).hexdigest()
        bur1_pw = hashlib.sha256("123".encode()).hexdigest()
        cur.execute("INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("dispatcher", "Диспетчер", dispatcher_pw, "dispatcher", datetime.utcnow().isoformat()))
        cur.execute("INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("bur1", "Буровик 1", bur1_pw, "driller", datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()

# -----------------------
# Supabase (HTTP) helpers
# -----------------------
async def supabase_get(table: str, params: str = "") -> typing.Any:
    """
    GET from Supabase REST. params should start with ? if provided.
    """
    if not USE_SUPABASE:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

async def supabase_post(table: str, payload: dict) -> typing.Any:
    if not USE_SUPABASE:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

# -----------------------
# Utility: current user
# -----------------------
def get_current_user(request: Request):
    return request.session.get("user")

# -----------------------
# Startup: try to connect Supabase, else init sqlite
# -----------------------
@app.on_event("startup")
async def startup_event():
    global USE_SUPABASE, USE_SQLITE
    if USE_SUPABASE:
        # quick test: try to read users (limit 1)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                test_url = f"{SUPABASE_URL}/rest/v1/users?select=*&limit=1"
                r = await client.get(test_url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
                if r.status_code in (200, 206):
                    print("Supabase reachable — using Supabase REST.")
                    USE_SQLITE = False
                else:
                    print("Supabase returned status", r.status_code, "— falling back to SQLite")
                    USE_SUPABASE = False
                    USE_SQLITE = True
        except Exception as e:
            print("Supabase connect/create error:", e)
            USE_SUPABASE = False
            USE_SQLITE = True
    else:
        USE_SQLITE = True

    if USE_SQLITE:
        init_sqlite()

    # When using Supabase and users table empty, try to create default accounts there
    if USE_SUPABASE:
        try:
            users = await supabase_get("users", "?select=id&limit=1")
            if not users:
                print("Supabase users empty — creating default dispatcher and bur1")
                # create dispatcher and bur1 with bcrypt
                try:
                    await supabase_post("users", {
                        "username": "dispatcher",
                        "full_name": "Диспетчер",
                        "password_hash": pwd_context.hash("1234"),
                        "role": "dispatcher",
                        "created_at": datetime.utcnow().isoformat()
                    })
                except httpx.HTTPStatusError as e:
                    # handle duplicate or other errors gracefully
                    print("Could not insert dispatcher (maybe exists):", e.response.status_code, getattr(e.response, "text", ""))
                try:
                    await supabase_post("users", {
                        "username": "bur1",
                        "full_name": "Буровик 1",
                        "password_hash": pwd_context.hash("123"),
                        "role": "driller",
                        "created_at": datetime.utcnow().isoformat()
                    })
                except httpx.HTTPStatusError as e:
                    print("Could not insert bur1 (maybe exists):", e.response.status_code, getattr(e.response, "text", ""))
        except Exception as e:
            print("Supabase error during startup (fallback to sqlite):", e)
            USE_SUPABASE = False
            USE_SQLITE = True
            init_sqlite()

# -----------------------
# Password check helper
# -----------------------
def check_password_from_db(plain_password: str, stored_hash: typing.Optional[str]) -> bool:
    """
    Support bcrypt (Passlib) and legacy SHA256 hex string.
    """
    if not stored_hash:
        return False
    stored = stored_hash.strip()
    # bcrypt style
    if stored.startswith("$2a$") or stored.startswith("$2b$") or stored.startswith("$2y$"):
        try:
            return pwd_context.verify(plain_password, stored)
        except Exception:
            return False
    # likely hex sha256
    if len(stored) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored):
        return hashlib.sha256(plain_password.encode()).hexdigest() == stored.lower()
    # fallback try passlib then sha256
    try:
        if pwd_context.verify(plain_password, stored):
            return True
    except Exception:
        pass
    return hashlib.sha256(plain_password.encode()).hexdigest() == stored.lower()

# -----------------------
# ROUTES
# -----------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Try Supabase first if enabled
    user = None
    if USE_SUPABASE:
        try:
            users = await supabase_get("users", f"?select=*&username=eq.{username}")
            if users:
                user = users[0]
        except Exception as e:
            print("Supabase read error during login, falling back to sqlite:", e)
            user = None

    if not user and USE_SQLITE:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = ?", (username,))
            r = cur.fetchone()
            if r:
                user = dict(r)
            conn.close()
        except Exception as e:
            print("SQLite read error:", e)
            user = None

    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    stored_hash = user.get("password_hash") or user.get("password")
    if not check_password_from_db(password, stored_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    safe_user = {
        "id": user.get("id"),
        "username": user.get("username"),
        "full_name": user.get("full_name") or user.get("fio") or user.get("username"),
        "role": user.get("role") or user.get("roles") or "driller"
    }
    request.session["user"] = safe_user

    if safe_user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# -----------------------
# Bur form (driller)
# -----------------------
@app.get("/burform", response_class=HTMLResponse)
async def bur_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request, "user": user})

@app.post("/submit_report")
async def submit_report(
    request: Request,
    area: str = Form(...),
    rig: str = Form(...),
    meter: str = Form(...),
    pogon: str = Form(""),
    operation: str = Form(...),
    person: str = Form(""),
    note: str = Form("")
):
    created_at = datetime.utcnow().isoformat()
    payload = {
        "date": datetime.utcnow().date().isoformat(),
        "time": datetime.utcnow().time().strftime("%H:%M:%S"),
        "section": area,
        "rig_number": rig,
        "meterage": meter,
        "pogonometr": pogon,
        "operation_type": operation,
        "operator_name": person,
        "note": note,
        "created_at": created_at
    }

    if USE_SUPABASE:
        try:
            await supabase_post("reports", payload)
        except Exception as e:
            print("Failed to POST report to Supabase:", e)
            # fallback to sqlite insert
            try:
                conn = sqlite_connect()
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO reports (date, time, section, rig_number, meterage, pogonometr, operation_type, operator_name, note, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (payload["date"], payload["time"], payload["section"], payload["rig_number"],
                     payload["meterage"], payload["pogonometr"], payload["operation_type"],
                     payload["operator_name"], payload["note"], payload["created_at"])
                )
                conn.commit()
                conn.close()
            except Exception as e2:
                print("Failed to write report to SQLite fallback:", e2)
    else:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO reports (date, time, section, rig_number, meterage, pogonometr, operation_type, operator_name, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload["date"], payload["time"], payload["section"], payload["rig_number"],
                 payload["meterage"], payload["pogonometr"], payload["operation_type"],
                 payload["operator_name"], payload["note"], payload["created_at"])
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print("SQLite report insert error:", e)

    return RedirectResponse("/burform", status_code=302)

# -----------------------
# Dispatcher page
# -----------------------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    reports = []
    if USE_SUPABASE:
        try:
            params = "?select=*&order=created_at.desc"
            if section:
                params = f"?select=*&order=created_at.desc&section=eq.{section}"
            reports = await supabase_get("reports", params)
        except Exception as e:
            print("dispatcher_page supabase_get error:", e)
            try:
                conn = sqlite_connect()
                cur = conn.cursor()
                cur.execute("SELECT * FROM reports ORDER BY id DESC")
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                reports = rows
            except Exception as e2:
                print("dispatcher_page sqlite read error:", e2)
                reports = []
    else:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute("SELECT * FROM reports ORDER BY id DESC")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            reports = rows
        except Exception as e:
            print("dispatcher_page sqlite read error:", e)
            reports = []

    sites = ['', 'Хорасан', 'Заречное', 'Карамурын', 'Ирколь', 'Степногорск']
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "sites": sites, "selected_site": section or ""})

# -----------------------
# Export Excel
# -----------------------
@app.get("/export_excel")
async def export_excel(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    reports = []
    if USE_SUPABASE:
        try:
            params = "?select=*&order=created_at.desc"
            if section:
                params = f"?select=*&order=created_at.desc&section=eq.{section}"
            reports = await supabase_get("reports", params)
        except Exception as e:
            print("export_excel supabase_get error:", e)
            reports = []
    else:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute("SELECT * FROM reports ORDER BY id DESC")
            reports = [dict(r) for r in cur.fetchall()]
            conn.close()
        except Exception as e:
            print("export_excel sqlite read error:", e)
            reports = []

    wb = Workbook()
    ws = wb.active
    ws.title = "reports"
    ws.append([
        "ID", "Дата UTC", "Участок", "Номер агрегата", "Метраж", "Погонометр",
        "Операция", "Автор", "Примечание"
    ])
    for r in reports:
        created = r.get("created_at") or ""
        ws.append([
            r.get("id"),
            created,
            r.get("section") or r.get("location"),
            r.get("rig_number"),
            r.get("meterage"),
            r.get("pogonometr"),
            r.get("operation_type") or r.get("operation"),
            r.get("operator_name"),
            r.get("note") or ""
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# -----------------------
# Users page (dispatcher)
# -----------------------
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    users = []
    if USE_SUPABASE:
        try:
            users = await supabase_get("users", "?select=id,username,full_name,role,created_at")
        except Exception as e:
            print("users_page supabase_get error:", e)
            users = []
    else:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute("SELECT id, username, full_name, role, created_at FROM users")
            users = [dict(r) for r in cur.fetchall()]
            conn.close()
        except Exception as e:
            print("users_page sqlite read error:", e)
            users = []

    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": users})

# -----------------------
# Create user (dispatcher)
# -----------------------
@app.post("/create_user")
async def create_user(request: Request,
                      username: str = Form(...),
                      full_name: str = Form(""),
                      password: str = Form(...),
                      role: str = Form("driller")):
    admin = get_current_user(request)
    if not admin or admin.get("role") != "dispatcher":
        return RedirectResponse("/login")

    hashed = pwd_context.hash(password)
    payload = {
        "username": username,
        "full_name": full_name,
        "password_hash": hashed,
        "role": role,
        "created_at": datetime.utcnow().isoformat()
    }

    if USE_SUPABASE:
        try:
            await supabase_post("users", payload)
        except httpx.HTTPStatusError as e:
            # If duplicate username, return friendly error (avoid crash)
            code = getattr(e.response, "status_code", None)
            text = getattr(e.response, "text", "")
            if code == 409 or (isinstance(text, str) and "duplicate" in text.lower()):
                return JSONResponse({"error": "username already exists"}, status_code=400)
            print("create_user supabase_post error:", e)
            return JSONResponse({"error": "Failed to create user in Supabase", "details": text}, status_code=500)
        except Exception as e:
            print("create_user supabase error:", e)
            return JSONResponse({"error": "Failed to create user in Supabase", "details": str(e)}, status_code=500)
    else:
        try:
            conn = sqlite_connect()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                        (username, full_name, hashed, role, payload["created_at"]))
            conn.commit()
            conn.close()
        except Exception as e:
            print("create_user sqlite error:", e)
            return JSONResponse({"error": "Failed to create user in SQLite", "details": str(e)}, status_code=500)

    return RedirectResponse("/users", status_code=303)

# -----------------------
# Healthcheck
# -----------------------
@app.get("/ping")
def ping():
    return {"status": "ok", "use_supabase": USE_SUPABASE}

# -----------------------
# Friendly error handler for debugging (optional)
# -----------------------
@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    print("Unhandled exception:", exc)
    traceback.print_exc()
    return JSONResponse({"error": str(exc)}, status_code=500)
