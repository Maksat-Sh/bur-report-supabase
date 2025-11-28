from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import httpx
import os

app = FastAPI()

# ---------- SETTINGS ----------
SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- AUTH HELPERS ----------
def require_login(request: Request):
    return "user" in request.session


async def get_user(username: str):
    """Получить юзера из таблицы users"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None


# ---------- ROUTES ----------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # 1. Диспетчер
    if username == "admin" and password == "1234":
        request.session["user"] = {"username": "admin", "role": "admin"}
        return RedirectResponse("/dispatcher", status_code=302)

    # 2. Буровик – ищем в таблице users
    user = await get_user(username)

    if user and str(user.get("password")) == password:
        request.session["user"] = {
            "username": username,
            "full_name": user.get("full_name"),
            "location": user.get("location"),
            "role": "worker"
        }
        return RedirectResponse("/burform", status_code=302)

    return RedirectResponse("/login?error=1", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------- БУРОВАЯ ФОРМА ----------
@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    if not require_login(request):
        return RedirectResponse("/login")

    user = request.session["user"]

    if user["role"] != "worker":
        return RedirectResponse("/login")

    return templates.TemplateResponse("burform.html", {
        "request": request,
        "user": user
    })


# ---------- ПРИЕМ СВОДКИ ----------
@app.post("/submit_report")
async def submit_report(
    request: Request,
    section: str = Form(...),
    bur_no: str = Form(...),
    pogonometr: float = Form(...),
    footage: float = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form(...)
):

    user = request.session["user"]

    data = {
        "bur": user["full_name"],            # ФИО буровика
        "location": user["location"],        # участок
        "section": section,
        "bur_no": bur_no,
        "pogonometr": pogonometr,
        "footage": footage,
        "operation_type": operation_type,
        "operation": operation,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/reports",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json=data
        )

        if resp.status_code >= 300:
            return RedirectResponse("/burform?fail=1", status_code=302)

    return RedirectResponse("/burform?ok=1", status_code=302)


# ---------- API: Загрузка сводок для диспетчера ----------
@app.get("/api/reports")
async def api_reports(request: Request, location: str = None):
    if not require_login(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    query = "reports"
    if location:
        query += f"?location=eq.{location}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{query}&order=created_at.desc",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return resp.json()


# ---------- ДИСПЕТЧЕР ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not require_login(request):
        return RedirectResponse("/login")

    if request.session["user"]["role"] != "admin":
        return RedirectResponse("/login")

    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.on_event("startup")
async def startup_event():
    print("Supabase REST ready:", SUPABASE_URL)
