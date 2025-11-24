# main.py — универсальный сервер: Supabase REST или локальная SQLite (fallback)
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
import sqlite3
import typing
from passlib.context import CryptContext

# load .env (useful locally)
load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecretkey"))

# templates + static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# password helpers
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# config: supabase / local DB
SUPABASE_URL = os.getenv("SUPABASE_URL")  # e.g. https://xxx.supabase.co
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# local sqlite path
SQLITE_PATH = os.getenv("SQLITE_PATH", "database.db")

# ---------------------------
# Supabase HTTP helpers
# ---------------------------
async def supabase_get(table: str, params: str = "") -> typing.Any:
    """GET rows from Supabase REST. Raises httpx.HTTPStatusError if auth fails."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

async def supabase_post(table: str, payload: dict) -> typing.Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

# ---------------------------
# local sqlite helpers
# ---------------------------
def ensure_sqlite():
    """Create sqlite file and tables if missing."""
    conn = sqlite3.connect(SQLITE_PATH)
    c = conn.cursor()
    # users: username unique, password stored as sha256 hex, role
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT
    )
    """)
    # reports
    c.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        date TEXT,
        time TEXT,
        section TEXT,
        rig_number TEXT,
        meterage TEXT,
        pogonometr TEXT,
        operation TEXT,
        operator_name TEXT,
        note TEXT
    )
    """)
    conn.commit()
    conn.close()

def sqlite_get_user(username: str):
    conn = sqlite3.connect(SQLITE_PATH)
    c = conn.cursor()
    c.execute("SELECT username, password_hash, role FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"username": row[0], "password_hash": row[1], "role": row[2]}

def sqlite_create_user(username: str, password_plain: str, role: str):
    # store sha256 hex to be simple and deterministic
    ph = hashlib.sha256(password_plain.encode()).hexdigest()
    conn = sqlite3.connect(SQLITE_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                  (username, ph, role))
        conn.commit()
    finally:
        conn.close()

# ---------------------------
# password verification helper
# supports bcrypt stored hashes, sha256 hex, or plain sha256 compare
# ---------------------------
def check_password_from_db(plain_password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    s = stored_hash.strip()
    # bcrypt (passlib)
    if s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$"):
        try:
            return pwd_context.verify(plain_password, s)
        except Exception:
            return False
    # sha256 hex
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        return hashlib.sha256(plain_password.encode()).hexdigest() == s.lower()
    # fallback: direct compare (if someone stored plaintext — unlikely)
    return plain_password == s

# ---------------------------
# startup: ensure either supabase users exist or create sqlite fallback
# ---------------------------
@app.on_event("startup")
async def startup():
    # try to ensure supabase has default users (store sha256 hash there)
    created_local = False
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            # check if table exists by fetching
            users = await supabase_get("users", "?select=username")
            # if users missing / empty, create dispatcher and bur1
            if not users:
                # create dispatcher and bur1 with sha256 password hashes
                dispatcher_hash = hashlib.sha256("1234".encode()).hexdigest()
                bur1_hash = hashlib.sha256("123".encode()).hexdigest()
                await supabase_post("users", {"username": "dispatcher", "password_hash": dispatcher_hash, "role": "dispatcher"})
                await supabase_post("users", {"username": "bur1", "password_hash": bur1_hash, "role": "bur"})
        except httpx.HTTPStatusError as e:
            # unauthorized or other HTTP error — fallback to sqlite
            print("Supabase HTTP error during startup:", e)
            ensure_sqlite()
            sqlite_create_user("dispatcher", "1234", "dispatcher")
            sqlite_create_user("bur1", "123", "bur")
            created_local = True
        except Exception as e:
            # network error, etc. fallback
            print("Supabase error during startup (fallback to sqlite):", e)
            ensure_sqlite()
            sqlite_create_user("dispatcher", "1234", "dispatcher")
            sqlite_create_user("bur1", "123", "bur")
            created_local = True
    else:
        # supabase not configured -> local sqlite
        ensure_sqlite()
        sqlite_create_user("dispatcher", "1234", "dispatcher")
        sqlite_create_user("bur1", "123", "bur")
        created_local = True

    if created_local:
        print("Using local SQLite fallback. Users dispatcher/1234 and bur1/123 created (sha256).")

# ---------------------------
# UTIL: get_current_user from session
# ---------------------------
def get_current_user(request: Request):
    return request.session.get("user")

# ---------------------------
# ROUTES
# ---------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Try Supabase first (if configured). If Supabase fails or user not found there,
    try local sqlite fallback.
    """
    # Try Supabase if configured
    user = None
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            rows = await supabase_get("users", f"?select=*&username=eq.{username}")
            if rows:
                # supabase returns list of dicts
                row = rows[0]
                user = {
                    "username": row.get("username"),
                    "password_hash": row.get("password_hash"),
                    "role": row.get("role")
                }
        except Exception as e:
            # treat as fallback to sqlite
            print("Supabase read error during login, falling back to sqlite:", e)
            user = None

    # If not found in supabase, try sqlite
    if not user:
        u = sqlite_get_user(username)
        if u:
            user = u

    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    if not check_password_from_db(password, user.get("password_hash", "")):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    # store minimal user info in session
    request.session["user"] = {"username": user["username"], "role": user.get("role", "bur")}

    # redirect by role
    if request.session["user"]["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/burform", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# Dispatcher page — shows reports
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    # try to fetch reports from supabase; if not -> from sqlite
    reports = []
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            reports = await supabase_get("reports", "?select=*&order=created_at.desc")
        except Exception as e:
            print("Supabase reports read error, falling back to sqlite:", e)
            # fallthrough to sqlite
            reports = []

    if not reports:
        # read from sqlite
        ensure_sqlite()
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, created_at, date, time, section, rig_number, meterage, pogonometr, operation, operator_name, note FROM reports ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        # Normalize to dicts for template
        reports = [
            {
                "id": r[0],
                "created_at": r[1],
                "date": r[2],
                "time": r[3],
                "section": r[4],
                "rig_number": r[5],
                "meterage": r[6],
                "pogonometr": r[7],
                "operation": r[8],
                "operator_name": r[9],
                "note": r[10]
            } for r in rows
        ]

    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports})

# Bur form (driller)
@app.get("/burform", response_class=HTMLResponse)
def bur_form(request: Request):
    user = get_current_user(request)
    if not user:
        # allow redirect to login if not in session
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request, "user": user})

@app.post("/submit")
async def submit_report(request: Request,
                        date: str = Form(...),
                        time: str = Form(...),
                        site: str = Form(...),
                        rig_number: str = Form(...),
                        meterage: str = Form(...),
                        pogon: str = Form(...),
                        operation: str = Form(""),
                        operator_name: str = Form(""),
                        note: str = Form("")):
    payload = {
        "date": date,
        "time": time,
        "section": site,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogonometr": pogon,
        "operation": operation,
        "operator_name": operator_name,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    saved = False
    # try supabase
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            await supabase_post("reports", payload)
            saved = True
        except Exception as e:
            print("Supabase save error (falling back to sqlite):", e)
            saved = False

    if not saved:
        ensure_sqlite()
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO reports (created_at, date, time, section, rig_number, meterage, pogonometr, operation, operator_name, note)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (payload["created_at"], payload["date"], payload["time"], payload["section"],
                   payload["rig_number"], payload["meterage"], payload["pogonometr"], payload["operation"],
                   payload["operator_name"], payload["note"]))
        conn.commit()
        conn.close()

    return {"message": "Report submitted successfully"}

# Export excel (dispatcher)
@app.get("/export_excel")
async def export_excel(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    # fetch reports same as dispatcher_page
    # try supabase first
    reports = []
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            reports = await supabase_get("reports", "?select=*&order=created_at.desc")
        except Exception:
            reports = []

    if not reports:
        ensure_sqlite()
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, created_at, date, time, section, rig_number, meterage, pogonometr, operation, operator_name, note FROM reports ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        reports = [
            {
                "id": r[0],
                "created_at": r[1],
                "date": r[2],
                "time": r[3],
                "section": r[4],
                "rig_number": r[5],
                "meterage": r[6],
                "pogonometr": r[7],
                "operation": r[8],
                "operator_name": r[9],
                "note": r[10]
            } for r in rows
        ]

    wb = Workbook()
    ws = wb.active
    ws.title = "reports"
    ws.append(["ID", "Created_at", "Date", "Time", "Section", "Rig", "Meterage", "Pogonometr", "Operation", "Author", "Note"])
    for r in reports:
        ws.append([
            r.get("id"),
            r.get("created_at"),
            r.get("date"),
            r.get("time"),
            r.get("section"),
            r.get("rig_number"),
            r.get("meterage"),
            r.get("pogonometr"),
            r.get("operation"),
            r.get("operator_name"),
            r.get("note")
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# basic healthcheck
@app.get("/ping")
def ping():
    return {"status": "ok"}
