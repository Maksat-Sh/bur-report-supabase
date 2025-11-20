from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import bcrypt
import os
from datetime import datetime

# -----------------------------
#   SUPABASE CONFIG
# -----------------------------
SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92a2Zha3B3Z3ZycGJuamJya3phIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Njc5NTEyMywiZXhwIjoyMDcyMzcxMTIzfQ.PYn5uo29ucIel9XcMDXph7JDQPEfHFu0QC-axDb-774"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# -----------------------------
#   FASTAPI APP
# -----------------------------
app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# -----------------------------
#  SUPABASE FUNCTIONS
# -----------------------------
async def supabase_get(table, query=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{query}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=SUPABASE_HEADERS)
    if r.status_code != 200:
        return []
    return r.json()


async def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=data, headers=SUPABASE_HEADERS)
    return r.status_code in (200, 201)


# -----------------------------
#   ROUTES
# -----------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await supabase_get("users", f"?select=*&username=eq.{username}")

    if not users:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный логин"
        })

    user = users[0]

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный пароль"
        })

    request.session["user"] = user

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    return RedirectResponse("/report-form", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/report-form", response_class=HTMLResponse)
async def report_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")

    reports = await supabase_get("reports")
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})


# ---------------------------------------------
#   CREATE USER (API)
# ---------------------------------------------
@app.post("/create_user")
async def create_user(username: str = Form(...), password: str = Form(...), full_name: str = Form(...)):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    data = {
        "username": username,
        "password_hash": hashed,
        "full_name": full_name,
        "role": "driller",
        "created_at": datetime.utcnow().isoformat()
    }

    ok = await supabase_insert("users", data)

    if ok:
        return {"status": "success"}

    raise HTTPException(status_code=400, detail="Ошибка при создании пользователя")
