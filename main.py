from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from passlib.hash import bcrypt
import pandas as pd
from pydantic import BaseModel
import os
from datetime import datetime
from supabase import create_client, Client

# === Настройки Supabase ===
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://your-url.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your-anon-key")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Настройки FastAPI ===
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# === Модели ===
class Report(BaseModel):
    date: str
    time: str
    location: str
    rig_number: str
    meterage: float
    pogonometr: float
    notes: str

# === Вспомогательные функции ===
async def get_user_by_username(username: str):
    res = supabase.table("users").select("*").eq("username", username).execute()
    users = res.data
    return users[0] if users else None


def verify_password_plain_or_hash(plain_password: str, stored_user):
    """Проверяет пароль — поддерживает bcrypt и открытый текст"""
    if isinstance(stored_user, str):
        # если по ошибке передали строку, просто сравни напрямую
        return plain_password == stored_user
    if not stored_user:
        return False
    ph = stored_user.get("password_hash") or stored_user.get("password")
    if not ph:
        return False
    try:
        if ph.startswith("$2b$"):  # bcrypt
            return pwd_context.verify(plain_password, ph)
        return plain_password == ph
    except Exception:
        return False


def make_auth_response(url, username, role):
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("auth_user", username)
    response.set_cookie("auth_role", role)
    return response


def require_role(request: Request, roles: list[str]):
    role = request.cookies.get("auth_role")
    username = request.cookies.get("auth_user")
    if not role or role not in roles:
        return None
    return {"username": username, "role": role}


async def supabase_get(table, params=None):
    query = supabase.table(table).select("*")
    if params and "select" in params:
        query = supabase.table(table).select(params["select"])
    res = query.execute()
    return res.data


# === Роуты ===

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login_dispatcher")


# === Логин диспетчера ===
@app.get("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher_get(request: Request):
    return templates.TemplateResponse("login_dispatcher.html", {"request": request})


@app.post("/login_dispatcher")
async def login_dispatcher_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    user = await get_user_by_username(username)
    if not user or not verify_password_plain_or_hash(password, user):
        return templates.TemplateResponse(
            "login_dispatcher.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    role = user.get("role", "dispatcher")
    return make_auth_response("/dispatcher", username, role)


# === Страница диспетчера ===
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    auth = require_role(request, ["dispatcher", "admin"])
    if not auth:
        return RedirectResponse("/login_dispatcher")

    reports = await supabase_get("reports")
    try:
        reports_sorted = sorted(reports, key=lambda r: r.get("created_at") or "", reverse=True)
    except Exception:
        reports_sorted = reports

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": auth["username"], "reports": reports_sorted}
    )


# === Экспорт в Excel ===
@app.get("/export_excel")
async def export_excel(request: Request):
    auth = require_role(request, ["dispatcher", "admin"])
    if not auth:
        return RedirectResponse("/login_dispatcher")

    reports = await supabase_get("reports")
    df = pd.DataFrame(reports)
    filename = "/tmp/reports.xlsx"
    df.to_excel(filename, index=False)
    from fastapi.responses import FileResponse
    return FileResponse(filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="Сводка.xlsx")


# === Форма буровика ===
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/submit")
async def submit_form(
    request: Request,
    date: str = Form(...),
    time: str = Form(...),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogonometr: float = Form(...),
    notes: str = Form(...)
):
    report = {
        "date": date,
        "time": time,
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogonometr": pogonometr,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat()
    }
    supabase.table("reports").insert(report).execute()
    return RedirectResponse("/form", status_code=303)
