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

from fastapi.responses import HTMLResponse

# --- Страница входа буровика ---
@app.get("/login_worker", response_class=HTMLResponse)
async def login_worker_form():
    return """
    <html>
    <head>
        <title>Вход буровика</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <h2>Форма буровика</h2>
        <form id="workerForm">
            <label>Участок:</label><br>
            <input type="text" id="site" required><br><br>
            
            <label>Номер буровой установки:</label><br>
            <input type="text" id="rig_number" required><br><br>
            
            <label>Метраж:</label><br>
            <input type="number" id="footage" required><br><br>
            
            <label>Погонометр:</label><br>
            <input type="number" id="pogon" required><br><br>
            
            <label>Примечание:</label><br>
            <textarea id="note"></textarea><br><br>
            
            <button type="submit">Отправить сводку</button>
        </form>
        <p id="message" style="color:green;"></p>

        <script>
        document.getElementById("workerForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            const data = {
                site: document.getElementById("site").value,
                rig_number: document.getElementById("rig_number").value,
                footage: document.getElementById("footage").value,
                pogon: document.getElementById("pogon").value,
                note: document.getElementById("note").value
            };

            const res = await fetch("/submit_worker_report", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(data)
            });

            const result = await res.json();
            document.getElementById("message").textContent = result.message;

            if (res.ok) {
                document.getElementById("workerForm").reset();
            }
        });
        </script>
    </body>
    </html>
    """

@app.post("/login_dispatcher")
async def login_dispatcher_post(request: Request):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    user = await get_user_by_username(username)
    if not user or not verify_password_plain_or_hash(password, user["password"]):
        return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин или пароль"})
    response = RedirectResponse(url="/dispatcher", status_code=303)
    response.set_cookie(key="username", value=username)
    return response


# 👇 вот здесь вставь этот код — строго без лишних пробелов перед @
from datetime import datetime

@app.post("/submit_worker_report")
async def submit_worker_report(report: dict):
    try:
        data = {
            "site": report["site"],
            "rig_number": report["rig_number"],
            "footage": report["footage"],
            "pogon": report["pogon"],
            "note": report.get("note", ""),
            "created_at": datetime.utcnow().isoformat()
        }
        supabase.table("reports").insert(data).execute()
        return {"message": "Сводка успешно отправлена!"}
    except Exception as e:
        return {"message": f"Ошибка при сохранении: {str(e)}"}


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
