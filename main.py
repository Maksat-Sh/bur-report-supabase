# ---- main.py (полностью новый КОПИРУЙ ЦЕЛИКОМ) ----

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.sessions import SessionMiddleware
import httpx
import bcrypt
import os

SUPA_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co/rest/v1"
SUPA_KEY = "public"   # <-- ничего не меняй

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SECRETKEY123")


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- utils ---------------

async def supa_select(table, params=""):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPA_URL}/{table}?{params}",
            headers={"apikey": SUPA_KEY}
        )
        r.raise_for_status()
        return r.json()


async def supa_insert(table, data):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPA_URL}/{table}",
            json=data,
            headers={
                "apikey": SUPA_KEY,
                "Content-Type": "application/json"
            }
        )
        r.raise_for_status()
        return r.json()


# ========== AUTH ==================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if request.session.get("user"):
        role = request.session["user"]["role"]
        if role == "dispatcher":
            return RedirectResponse("/dispatcher")
        return RedirectResponse("/burform")
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await supa_select("users", f"username=eq.{username}")
    if not users:
        return RedirectResponse("/login?error=1", 303)

    user = users[0]

    hashed = user.get("password_hash", "")
    if not bcrypt.checkpw(password.encode(), hashed.encode()):
        return RedirectResponse("/login?error=1", 303)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"]
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", 302)
    return RedirectResponse("/burform", 302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)



#   ================= USERS (диспетчер) ===============


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    u = request.session.get("user")
    if not u or u["role"] != "dispatcher":
        return RedirectResponse("/login")

    all_users = await supa_select("users")
    return templates.TemplateResponse("users.html",
        {"request": request, "users": all_users})


@app.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...)
):
    u = request.session.get("user")
    if not u or u["role"] != "dispatcher":
        return RedirectResponse("/login")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await supa_insert("users", {
        "username": username,
        "full_name": full_name,
        "role": "bur",
        "password_hash": hashed
    })

    return RedirectResponse("/users", 302)



# --------------- dispatcher home --------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    u = request.session.get("user")
    if not u or u["role"] != "dispatcher":
        return RedirectResponse("/login")

    return templates.TemplateResponse("dispatcher.html", {"request": request})



# ------------ burform --------------

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    u = request.session.get("user")
    if not u:
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/burform_submit")
async def burform_submit(
    request: Request,
    section: str = Form(...),
    bur: str = Form(...),
    bur_no: str = Form(...),
    location: str = Form(...),
    footage: int = Form(...),
    pogonometr: int = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form(...)
):

    await supa_insert("reports", {
        "section": section,
        "bur": bur,
        "bur_no": bur_no,
        "location": location,
        "footage": footage,
        "pogonometr": pogonometr,
        "operation_type": operation_type,
        "operation": operation,
        "note": note
    })

    return RedirectResponse("/burform", 302)
