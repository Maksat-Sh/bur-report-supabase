import os
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import sqlite3

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

USE_SUPABASE = True if SUPABASE_URL and SUPABASE_ANON_KEY else False
USE_SQLITE = not USE_SUPABASE

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="BUR_REPORT_SECRET_KEY")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# -------------------------------------------------------------------
# HELPERS: Supabase REST
# -------------------------------------------------------------------

async def supabase_get(table: str, query: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{query}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

async def supabase_post(table: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=data)
        r.raise_for_status()
        return r.json()

# -------------------------------------------------------------------
# USING PLAIN PASSWORDS — CHECK FUNCTION
# -------------------------------------------------------------------

def check_password_from_db(input_password: str, stored_password: str):
    return input_password == stored_password

# -------------------------------------------------------------------
# STARTUP: create default users in Supabase IF EMPTY
# -------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    global USE_SUPABASE, USE_SQLITE

    if USE_SUPABASE:
        try:
            users = await supabase_get("users", "?select=id&limit=1")

            if not users:
                print("Supabase users are empty — creating dispatcher + bur1")

                try:
                    await supabase_post("users", {
                        "username": "dispatcher",
                        "full_name": "Диспетчер",
                        "password_hash": "1234",   # ✔ plain password
                        "role": "dispatcher",
                        "created_at": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    print("dispatcher insert failed:", e)

                try:
                    await supabase_post("users", {
                        "username": "bur1",
                        "full_name": "Буровик 1",
                        "password_hash": "123",    # ✔ plain password
                        "role": "driller",
                        "created_at": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    print("bur1 insert failed:", e)

        except Exception as e:
            print("Supabase unreachable, fallback to sqlite:", e)
            USE_SUPABASE = False
            USE_SQLITE = True

# -------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------

@app.get("/")
async def root():
    return RedirectResponse("/login")


@app.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = None

    # Try Supabase
    if USE_SUPABASE:
        try:
            data = await supabase_get("users", f"?select=*&username=eq.{username}")
            if data:
                user = data[0]
        except Exception as e:
            print("Supabase read error:", e)

    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный логин"
        })

    stored_pw = user.get("password_hash") or ""

    if not check_password_from_db(password, stored_pw):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный пароль"
        })

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name", user["username"]),
        "role": user.get("role", "driller")
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

# -------------------------------------------------------------------

@app.get("/dispatcher")
async def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/burform")
async def burform(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "driller":
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request})

# -------------------------------------------------------------------

