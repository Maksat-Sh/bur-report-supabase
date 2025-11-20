from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from datetime import datetime
import hashlib
import httpx
import os

app = FastAPI()

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ovkfakpwgvrpbnjbrkza.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # ОБЯЗАТЕЛЬНО ВЫНЕСТИ В ПЕРЕМЕННЫЕ Render
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------
# УТИЛИТЫ Supabase
# ---------------------------------------------------

async def supabase_get(table, query=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{query}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=SUPABASE_HEADERS)
        if r.status_code != 200:
            print("GET ERROR:", r.text)
            return []
        return r.json()

async def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=SUPABASE_HEADERS, json=data)
        print("INSERT STATUS:", r.status_code, r.text)
        return r.status_code, r.text

# ---------------------------------------------------
# CORS
# ---------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# LOGIN PAGE
# ---------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# ---------------------------------------------------
# LOGIN HANDLER
# ---------------------------------------------------

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await supabase_get("users", f"?select=*&username=eq.{username}")

    if not users:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    user = users[0]

    # SHA256, как у тебя в БД
    given_hash = hashlib.sha256(password.encode()).hexdigest()

    if user.get("password_hash") != given_hash:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    request.session = {}
    request.session["user"] = user

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    if user["role"] == "driller":
        return RedirectResponse("/report-form", status_code=302)

    return RedirectResponse("/", status_code=302)

# ---------------------------------------------------
# LOGOUT
# ---------------------------------------------------

@app.get("/logout")
async def logout(request: Request):
    request.session = {}
    return RedirectResponse("/login")

# ---------------------------------------------------
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ (API)
# ---------------------------------------------------

@app.post("/create_user")
async def create_user(username: str, password: str, full_name: str = "", role: str = "driller"):
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    payload = {
        "username": username,
        "password_hash": password_hash,
        "full_name": full_name,
        "role": role,
        "created_at": datetime.utcnow().isoformat(),
    }

    status, text = await supabase_insert("users", payload)

    if status in (200, 201):
        return {"status": "ok", "user": username}

    return {"status": "error", "detail": text}

# ---------------------------------------------------
# СТРАНИЦЫ (для диспетчера и буровиков)
# ---------------------------------------------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/report-form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})
