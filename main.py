import os
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# === ВАЖНО ===
# Эти переменные ОБЯЗАТЕЛЬНО должны быть заполнены на Render
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("SUPABASE_URL или SUPABASE_KEY не установлены!")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------- USERS -----------------------------

async def get_user(username: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=headers,
            params={"select": "*", "username": f"eq.{username}"}
        )
        data = resp.json()
        return data[0] if data else None


async def create_user(username: str, password: str, role: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=headers,
            json={"username": username, "password": password, "role": role}
        )


# ---------------------- ROUTES -----------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = await get_user(username)

    if not user or user["password"] != password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный логин или пароль"
        })

    request.session["user"] = user
    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------------------- BURFORM -----------------------------

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/burform")
async def submit_burform(
    request: Request,
    uchastok: str = Form(...),
    rig: str = Form(...),
    metrazh: str = Form(...),
    pogon: str = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/reports",
            headers=headers,
            json={
                "username": user["username"],
                "uchastok": uchastok,
                "rig": rig,
                "metrazh": metrazh,
                "pogon": pogon,
                "operation": operation,
                "responsible": responsible,
                "note": note
            }
        )

    return templates.TemplateResponse("burform.html", {
        "request": request,
        "success": "Сводка отправлена!"
    })


# ---------------------- DISPATCHER -----------------------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/reports",
            headers=headers,
            params={"select": "*"}
        )

    reports = resp.json()

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports
    })
