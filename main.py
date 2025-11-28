# main.py
import os
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from datetime import datetime
from openpyxl import Workbook
from io import BytesIO
import hashlib

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecretkey"))

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# env
SUPABASE_URL = os.getenv("SUPABASE_URL")    # e.g. https://xxx.supabase.co
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")  # service_role or anon (prefer service_role for inserts)
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_API_KEY)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -----------------------
# Supabase helpers
# -----------------------
def _sb_headers(prefer: str | None = None):
    h = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
    }
    if prefer:
        h["Prefer"] = prefer
    return h

def sb_select(table: str, filters: str = ""):
    if not USE_SUPABASE:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if filters:
        url = f"{url}?{filters}"
    r = requests.get(url, headers=_sb_headers())
    try:
        return r.json() if r.status_code in (200, 206) else []
    except Exception:
        return []

def sb_insert(table: str, data: dict, prefer_return: bool = False):
    if not USE_SUPABASE:
        raise RuntimeError("Supabase not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = _sb_headers("return=representation" if prefer_return else None)
    headers["Content-Type"] = "application/json"
    r = requests.post(url, json=data, headers=headers, timeout=15)
    if r.status_code >= 300:
        # return r.text for debugging
        raise RuntimeError(f"Supabase insert error {r.status_code}: {r.text}")
    try:
        return r.json()
    except Exception:
        return []

def sb_patch(table: str, filters: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filters}"
    headers = _sb_headers()
    headers["Content-Type"] = "application/json"
    r = requests.patch(url, json=data, headers=headers)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase patch error {r.status_code}: {r.text}")
    return r.json()

# -----------------------
# Password check helper (supports bcrypt, plain, sha256-hex)
# -----------------------
def verify_password(plain: str, user_record: dict) -> bool:
    # Prefer password_hash (bcrypt)
    ph = user_record.get("password_hash")
    plain_stored = user_record.get("password")
    if ph:
        try:
            return pwd_ctx.verify(plain, ph)
        except Exception:
            pass
    if plain_stored is not None:
        # direct plain text (legacy)
        if plain == plain_stored:
            return True
    # check sha256 hex (legacy)
    possible_hex = user_record.get("password_hash") or user_record.get("pw") or ""
    if isinstance(possible_hex, str) and len(possible_hex) == 64 and all(c in "0123456789abcdefABCDEF" for c in possible_hex):
        return hashlib.sha256(plain.encode()).hexdigest() == possible_hex.lower()
    return False

# -----------------------
# Utility: get_user by username
# -----------------------
def get_user_by_username(username: str):
    if not USE_SUPABASE:
        return None
    users = sb_select("users", f"username=eq.{username}")
    return users[0] if users else None

# -----------------------
# ROUTES
# -----------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not USE_SUPABASE:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Supabase not configured"})

    user = get_user_by_username(username)
    if not user:
        return RedirectResponse("/login?error=1", status_code=302)

    try:
        if not verify_password(password, user):
            return RedirectResponse("/login?error=1", status_code=302)
    except Exception as e:
        print("verify_password error:", e)
        return RedirectResponse("/login?error=1", status_code=302)

    # Save safe session
    request.session["user"] = {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role") or "driller",
        "full_name": user.get("full_name") or user.get("fio") or user.get("username"),
        "section": user.get("section") or ""
    }

    role = request.session["user"]["role"]
    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# -----------------------
# Bur form (driller)
# -----------------------
SECTIONS = ["Хорасан", "Карамурын", "Ирколь", "Заречное", "Семизбай"]

@app.get("/burform", response_class=HTMLResponse)
def bur_form(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") == "dispatcher":
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request, "user": user, "sections": SECTIONS})

@app.post("/submit_report")
def submit_report(
    request: Request,
    section: str = Form(...),
    bur_no: str = Form(None),
    pogonometr: float = Form(...),
    footage: float = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form("")
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    # derive bur and bur_no from session if available
    bur = user.get("full_name")
    bur_no_val = user.get("username") if not bur_no else bur_no

    payload = {
        "bur": bur,
        "section": section,
        "bur_no": str(bur_no_val),
        "pogonometr": pogonometr,
        "footage": footage,
        "operation_type": operation_type,
        "operation": operation,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        sb_insert("reports", payload)
        return RedirectResponse("/burform?ok=1", status_code=302)
    except Exception as e:
        print("Failed to POST report:", e)
        return RedirectResponse("/burform?fail=1", status_code=302)

# -----------------------
# Dispatcher
# -----------------------
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request, section: str = ""):
    user = request.session.get("user")
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    try:
        if section:
            reports = sb_select("reports", f"section=eq.{section}&order=created_at.desc")
        else:
            reports = sb_select("reports", "order=created_at.desc")
    except Exception as e:
        print("dispatcher sb_select error:", e)
        reports = []

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "user": user,
        "reports": reports,
        "sections": SECTIONS,
        "selected_section": section
    })

# -----------------------
# Export Excel
# -----------------------
@app.get("/export_excel")
def export_excel(request: Request, section: str = ""):
    user = request.session.get("user")
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    try:
        if section:
            reports = sb_select("reports", f"section=eq.{section}&order=created_at.desc")
        else:
            reports = sb_select("reports", "order=created_at.desc")
    except Exception as e:
        print("export_excel sb_select error:", e)
        reports = []

    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Дата UTC", "Участок", "Номер агрегата", "Метраж", "Погонометр", "Операция", "Тип операции", "Автор", "Примечание"])
    for r in reports:
        ws.append([
            r.get("id"),
            r.get("created_at"),
            r.get("section") or r.get("location"),
            r.get("bur_no"),
            r.get("footage"),
            r.get("pogonometr"),
            r.get("operation"),
            r.get("operation_type"),
            r.get("bur"),
            r.get("note") or ""
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# -----------------------
# Users (dispatcher)
# -----------------------
@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    try:
        users = sb_select("users", "order=id.asc")
    except Exception as e:
        print("users_page sb_select error:", e)
        users = []
    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": users, "sections": SECTIONS})

@app.post("/create_user")
def create_user(request: Request, username: str = Form(...), password: str = Form(...), full_name: str = Form(""), role: str = Form("driller"), section: str = Form("") ):
    admin = request.session.get("user")
    if not admin or admin.get("role") != "dispatcher":
        return RedirectResponse("/login")
    # create both plain password and hashed password
    password_hash = pwd_ctx.hash(password)
    payload = {
        "username": username,
        "full_name": full_name,
        "password": password,  # legacy plain column
        "password_hash": password_hash,
        "role": role,
        "section": section,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        sb_insert("users", payload)
    except Exception as e:
        print("create_user error:", e)
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse("/users", status_code=303)

# -----------------------
# Health
# -----------------------
@app.get("/ping")
def ping():
    return {"status": "ok", "use_supabase": USE_SUPABASE}
