from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import httpx
from datetime import datetime
import os

app = FastAPI()

# ========================
#   CONFIG
# ========================
app.add_middleware(SessionMiddleware, secret_key="supersecret123")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Диспетчер логин/пароль
ADMIN_USER = "dispatcher"
ADMIN_PASS = "1234"


# ========================
#   ROUTES
# ========================

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        request.session["user"] = "dispatcher"
        return RedirectResponse("/dispatcher", status_code=302)

    # Буровик — всегда заходит без логина
    request.session["user"] = "bur"
    return RedirectResponse("/burform", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    if request.session.get("user") != "dispatcher":
        return RedirectResponse("/login")

    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/submit_report")
async def submit_report(
    request: Request,
    bur: str = Form(...),
    section: str = Form(...),
    location: str = Form(...),
    bur_no: str = Form(...),
    pogonometr: float = Form(...),
    footage: float = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form(...)
):

    location = section  # <==== вот эта строка решает ошибку

data = {
    "bur": bur,
    "section": section,
    "location": location,
    "bur_no": bur_no,
    "pogonometr": pogonometr,
    "footage": footage,
    "operation_type": operation_type,
    "operation": operation,
    "note": note,
    "created_at": datetime.utcnow().isoformat()
}


    print("=== REPORT DATA BEFORE SENDING TO SUPABASE ===")
    print(data)
    print("================================================")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/reports",
            headers=HEADERS,
            json=data
        )

    if response.status_code >= 300:
        print("Failed to POST report:", response.status_code, response.text)
        return RedirectResponse("/burform?fail=1", status_code=302)

    return RedirectResponse("/burform?ok=1", status_code=302)


# Получение всех отчётов для диспетчера
@app.get("/api/reports")
async def get_reports(request: Request):
    if request.session.get("user") != "dispatcher":
        return {"error": "Unauthorized"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/reports?select=*",
            headers=HEADERS
        )

    return response.json()
