# main.py — исправленный и устойчивый вариант для Supabase REST + Render
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

 #supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
 You can still run locally but many routes will fail if Supabase not configured.
   print("WARNING: SUPABASE_URL or SUPABASE_KEY not set in environment.")

# password contexts
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------
# Supabase helpers (HTTP)
# ---------------------------
async def supabase_get(table: str, params: str = "") -> typing.Any:
   url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
  headers = {
     "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

async def supabase_post(table: str, payload: dict) -> typing.Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

# ---------------------------
# utility: get current user from session
# ---------------------------
def get_current_user(request: Request):
    return request.session.get("user")

# ---------------------------
# startup — create default users if missing
# ---------------------------
@app.on_event("startup")
async def create_default_users():
    # only if supabase configured
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    # dispatcher
    try:
        existing = await supabase_get("users", "?select=*&username=eq.dispatcher")
        if not existing:
            payload = {
                "username": "dispatcher",
                "full_name": "Диспетчер",
                "password_hash": pwd_context.hash("1234"),
                "role": "dispatcher",
                "created_at": datetime.utcnow().isoformat()
            }
            await supabase_post("users", payload)
    except Exception as e:
        print("create_default_users (dispatcher) error:", e)

    # test drillers
    for u in ["bur1", "bur2", "bur3"]:
        try:
            existing = await supabase_get("users", f"?select=*&username=eq.{u}")
            if not existing:
                payload = {
                    "username": u,
                    "full_name": f"Буровик {u}",
                    "password_hash": pwd_context.hash("123"),
                    "role": "driller",
                    "created_at": datetime.utcnow().isoformat()
                }
                await supabase_post("users", payload)
        except Exception as e:
            print(f"create_default_users ({u}) error:", e)

# ---------------------------
# ROOT, LOGIN pages
# ---------------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# small helper to safely compare password hashes from DB:
def check_password_from_db(plain_password: str, stored_hash: str) -> bool:
    """
    Support bcrypt (Passlib) and legacy SHA256 hex string.
    - If stored_hash startswith $2 -> bcrypt
    - If stored_hash looks like 64 hex chars -> compare sha256
    - Else: try passlib verify and fallback to sha256 compare
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

    # fallback: try passlib (may raise) then sha256
    try:
        if pwd_context.verify(plain_password, stored):
            return True
    except Exception:
        pass

    # final fallback to sha256 hex
    return hashlib.sha256(plain_password.encode()).hexdigest() == stored.lower()

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # fetch user by username (Supabase REST)
    try:
        users = await supabase_get("users", f"?select=*&username=eq.{username}")
    except Exception as e:
        # supabase unavailable
        return templates.TemplateResponse("login.html", {"request": request, "error": f"Ошибка доступа к БД: {e}"})

    if not users:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    user = users[0]

    if not check_password_from_db(password, user.get("password_hash")):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    # save user in session
    request.session["user"] = user

    # route by role
    if user.get("role") == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    if user.get("role") == "driller":
        return RedirectResponse("/form", status_code=302)

    return RedirectResponse("/", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ---------------------------
# CREATE USER FORM (browser) - helps create bur1/bur2/bur3 without Postman
# GET shows simple form, POST creates user
# ---------------------------
@app.get("/create_user_form", response_class=HTMLResponse)
async def create_user_form(request: Request):
    return HTMLResponse("""
    <html><body>
      <h3>Create user</h3>
      <form method="post" action="/create_user_form">
        username: <input name="username"><br>
        password: <input name="password"><br>
        full_name: <input name="full_name"><br>
        role: <select name="role"><option value="driller">driller</option><option value="dispatcher">dispatcher</option></select><br>
        <button type="submit">Create</button>
      </form>
      <p>Or use /create_user?username=... (POST)</p>
    </body></html>
    """)

@app.post("/create_user_form")
async def create_user_form_post(request: Request, username: str = Form(...), password: str = Form(...), full_name: str = Form(""), role: str = Form("driller")):
    # create user (bcrypt hash)
    hashed = pwd_context.hash(password)
    payload = {
        "username": username,
        "full_name": full_name,
        "password_hash": hashed,
        "role": role,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        await supabase_post("users", payload)
    except httpx.HTTPStatusError as e:
        return HTMLResponse(f"Ошибка создания: {e.response.status_code} {e.response.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(f"Ошибка создания: {e}", status_code=400)

    return HTMLResponse(f"Пользователь {username} создан. <a href='/create_user_form'>Назад</a>")

# also keep POST /create_user as API (non-browser) — accepts form or query params via POST
@app.post("/create_user")
async def create_user(request: Request, username: str = Form(None), password: str = Form(None), full_name: str = Form(""), role: str = Form("driller")):
    # try query string fallback if form not provided
    if not username:
        qs = request.query_params
        username = qs.get("username")
        password = qs.get("password")
        full_name = qs.get("full_name", "")
        role = qs.get("role", "driller")

    if not username or not password:
        return {"error": "username and password required"}

    hashed = pwd_context.hash(password)
    payload = {
        "username": username,
        "full_name": full_name,
        "password_hash": hashed,
        "role": role,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        created = await supabase_post("users", payload)
    except httpx.HTTPStatusError as e:
        return {"error": f"{e.response.status_code} {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}

    return {"status": "ok", "user": created}

# ---------------------------
# REPORT FORM for drillers (simple)
# ---------------------------
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})

@app.post("/submit")
async def submit_report(
        date: str = Form(...),
        time: str = Form(...),
        site: str = Form(...),
        rig_number: str = Form(...),
        meterage: str = Form(...),
        pogon: str = Form(...),
        note: str = Form("")
):
    payload = {
        "date": date,
        "time": time,
        "section": site,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogonometr": pogon,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        await supabase_post("reports", payload)
    except Exception as e:
        return {"error": str(e)}

    return {"message": "Report submitted successfully"}

# ---------------------------
# dispatcher page + export excel
# ---------------------------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    params = "?select=*&order=created_at.desc"
    if section:
        params = f"?select=*&order=created_at.desc&section=eq.{section}"

    try:
        reports = await supabase_get("reports", params)
    except Exception as e:
        reports = []
        print("dispatcher_page supabase_get error:", e)

    sites = ['', 'Хорасан', 'Заречное', 'Карамурын', 'Ирколь', 'Степногорск']

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": user, "reports": reports, "sites": sites, "selected_site": section or ""}
    )

@app.get("/export_excel")
async def export_excel(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    params = "?select=*&order=created_at.desc"
    if section:
        params = f"?select=*&order=created_at.desc&section=eq.{section}"

    reports = []
    try:
        reports = await supabase_get("reports", params)
    except Exception as e:
        print("export_excel supabase_get error:", e)

    wb = Workbook()
    ws = wb.active
    ws.title = "reports"

    ws.append([
        "ID", "Дата UTC", "Участок", "Номер агрегата", "Метраж", "Погонометр",
        "Операция", "Автор", "Примечание"
    ])

    for r in reports:
        created = r.get("created_at") or r.get("timestamp") or ""
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
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'}
    )

# ---------------------------
# users page (dispatcher only)
# ---------------------------
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    try:
        users = await supabase_get("users", "?select=*")
    except Exception as e:
        users = []
        print("users_page supabase_get error:", e)

    sites = ['Хорасан', 'Заречное', 'Карамурын', 'Ирколь', 'Степногорск']

    return templates.TemplateResponse(
        "users.html",
        {"request": request, "user": user, "users": users, "sites": sites}
    )

# healthcheck
@app.get("/ping")
def ping():
    return {"status": "ok"}
