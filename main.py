import os
from urllib.parse import quote_plus

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

import httpx
from passlib.context import CryptContext

# Config from env
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")  # set in prod

if not SUPABASE_URL or not SUPABASE_KEY:
    # allow startup but warn — better to fail loudly in production
    print("WARNING: SUPABASE_URL or SUPABASE_KEY is not set. Some operations will fail.")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Templates + static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Password helper
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Sections for bur form
SECTIONS = [
    "Участок A", "Участок B", "Участок C"
]

# HTTP client settings
DEFAULT_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

async def supabase_select(table: str, filter_expr: str = None):
    """Select rows from supabase rest v1 table. filter_expr example: 'username=eq.someuser'"""
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL not set")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    if filter_expr:
        # safe pass as querystring param to supabase (httpx will URL-encode)
        params["q"] = filter_expr  # not standard, but we won't use - we use raw building
        # better: pass filter in full URL:
        url = url + "?" + filter_expr
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers=DEFAULT_HEADERS)
        r.raise_for_status()
        return r.json()

async def supabase_insert(table: str, payload: dict):
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL not set")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = DEFAULT_HEADERS.copy()
    headers.update({
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    })
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

# Routes

@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_get(request: Request, error: str | None = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        # Query user by username (use URL-encoding)
        # Supabase REST filter: ?username=eq.<value>
        escaped = quote_plus(username)
        url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{escaped}&select=*"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=DEFAULT_HEADERS)
            r.raise_for_status()
            users = r.json()
    except Exception as e:
        # log and return error
        print("Supabase select error:", e)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ошибка при проверке пользователя."})

    if not users:
        return RedirectResponse(url="/login?error=1", status_code=302)

    user = users[0]
    stored_hash = user.get("password_hash") or user.get("password") or ""
    # cleanup accidental newlines
    stored_hash = stored_hash.strip()

    try:
        if not pwd_context.verify(password, stored_hash):
            return RedirectResponse(url="/login?error=1", status_code=302)
    except Exception as e:
        print("Password verify error:", e)
        # Hash might be malformed or other issue
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ошибка аутентификации (формат хэша)."})

    # Auth OK
    request.session["user"] = {"id": user.get("id"), "username": user.get("username"), "role": user.get("role")}
    # redirect based on role
    if user.get("role") == "dispatcher":
        return RedirectResponse(url="/dispatcher", status_code=302)
    return RedirectResponse(url="/burform", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/login")


@app.get("/burform")
async def bur_get(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("burform.html", {"request": request, "user": user, "sections": SECTIONS})


@app.post("/api/reports")
async def create_report(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    form = await request.form()
    # collect fields from form (adjust names as in template)
    payload = {
        "created_at": form.get("created_at") or None,
        "section": form.get("section"),
        "driller": user.get("username"),
        "rig_number": form.get("rig_number"),
        "metrazh": form.get("metrazh"),
        "pogonometr": form.get("pogonometr"),
        "note": form.get("note"),
    }
    try:
        inserted = await supabase_insert("reports", payload)
    except Exception as e:
        print("Insert error:", e)
        raise HTTPException(status_code=500, detail="db insert error")
    return JSONResponse({"message": "Report submitted successfully", "data": inserted})


@app.get("/api/reports")
async def list_reports(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401)
    # fetch recent reports
    try:
        url = f"{SUPABASE_URL}/rest/v1/reports?select=*&order=created_at.desc"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=DEFAULT_HEADERS)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print("Select reports error:", e)
        raise HTTPException(status_code=500, detail="cannot fetch reports")
    return JSONResponse(data)


@app.get("/dispatcher")
async def dispatcher_view(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse(url="/login")
    # dispatcher template will call /api/reports via fetch
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user})
