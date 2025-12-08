from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from passlib.hash import argon2
from datetime import datetime
from typing import Optional
import httpx
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="secret123")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------------- HELPERS --------------------------
async def supabase_query(table: str, func: str, payload=None, where=None):
    async with httpx.AsyncClient() as client:
        url = f"{SUPABASE_URL}/rest/v1/{table}"

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        if where:
            url += f"?{where}"

        if func == "get":
            return (await client.get(url, headers=headers)).json()

        if func == "post":
            return (await client.post(url, headers=headers, json=payload)).json()

        if func == "patch":
            return (await client.patch(url, headers=headers, json=payload)).json()

        if func == "delete":
            return (await client.delete(url, headers=headers)).json()


def current_user(request: Request):
    return request.session.get("user")


def require_dispatcher(request: Request):
    u = current_user(request)
    if not u or u["role"] != "dispatcher":
        return RedirectResponse("/login", status_code=302)


# -------------------------- LOGIN --------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(), password: str = Form()):
    res = await supabase_query("users", "get", where=f"username=eq.{username}")

    if not res: 
        return RedirectResponse("/login?error=1", status_code=302)

    user = res[0]

   if not argon2.verify(password, user["password_hash"]):
        return RedirectResponse("/login?error=1", status_code=302)

    request.session["user"] = user

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher")
    else:
        return RedirectResponse("/burform")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -------------------------- BUR FORM --------------------------
@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    if not current_user(request):
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/burform")
async def submit_report(
    request: Request,
    section: str = Form(),
    bur_no: str = Form(),
    footage: int = Form(),
    pogonometr: int = Form(),
    operation_type: str = Form(),
    operation: str = Form(),
    responsible: str = Form(),
    note: str = Form(),
):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login")

    await supabase_query("reports", "post", {
        "section": section,
        "bur_no": bur_no,
        "footage": footage,
        "pogonometr": pogonometr,
        "operation_type": operation_type,
        "operation": operation,
        "responsible": responsible,
        "note": note,
        "created_at": datetime.utcnow().isoformat(),
        "bur": u["username"]
    })

    return RedirectResponse("/burform", status_code=302)


# -------------------------- DISPATCHER VIEW --------------------------
@app.get("/dispatcher")
async def dispatcher(request: Request):
    if require_dispatcher(request):
        return require_dispatcher(request)

    reports = await supabase_query("reports", "get")
    users = await supabase_query("users", "get")

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports,
        "users": users
    })


# -------------------------- CREATE USER --------------------------
@app.post("/create_user")
async def create_user(
    request: Request,
    username: str = Form(),
    full_name: str = Form(),
    password: str = Form(),
):
    if require_dispatcher(request):
        return require_dispatcher(request)

    hashed = bcrypt.hash(password)

    await supabase_query("users", "post", {
        "username": username,
        "full_name": full_name,
        "password_hash": hashed,
        "role": "bur",
        "created_at": datetime.utcnow().isoformat()
    })

    return RedirectResponse("/dispatcher", status_code=302)
