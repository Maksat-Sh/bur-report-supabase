import os
import io
import requests
import pandas as pd
from fastapi import FastAPI, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime

# Загрузка .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    import os
print("DEBUG SUPABASE_URL =", os.getenv("SUPABASE_URL"))
print("DEBUG SUPABASE_API_KEY =", os.getenv("SUPABASE_API_KEY"))

    raise RuntimeError("SUPABASE_URL или SUPABASE_API_KEY не найдены в .env")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

security = HTTPBasic()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- USERS ---
USERS = {
    "bur1": {"password": "123", "role": "driller", "full_name": "Бурильщик 1"},
    "bur2": {"password": "123", "role": "driller", "full_name": "Бурильщик 2"},
    "dispatcher": {"password": "dispatch123", "role": "dispatcher", "full_name": "Диспетчер"},
    "admin": {"password": "9999", "role": "admin", "full_name": "Администратор"},
}

# --- Авторизация ---
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user"):
        role = request.session["user"]["role"]
        if role == "dispatcher" or role == "admin":
            return RedirectResponse("/dispatcher")
        elif role == "driller":
            return RedirectResponse("/form")
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = USERS.get(username)
    if not user or user["password"] != password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    request.session["user"] = user
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# --- Форма буровика ---
@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "driller":
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})


@app.post("/submit")
def submit_report(
    request: Request,
    date_time: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(""),
    location: str = Form(...),
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    full_name = user["full_name"]

    report_data = {
        "date_time": date_time,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "operator_name": full_name,
        "location": location,
    }

    response = requests.post(f"{SUPABASE_URL}/rest/v1/reports", headers=SUPABASE_HEADERS, json=report_data)
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении отчёта: {response.text}")

    return {"message": "Сводка успешно отправлена!"}


# --- Интерфейс диспетчера ---
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] not in ("dispatcher", "admin"):
        return RedirectResponse("/login")

    response = requests.get(f"{SUPABASE_URL}/rest/v1/reports?select=*", headers=SUPABASE_HEADERS)
    reports = response.json() if response.status_code == 200 else []

    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports})


# --- Экспорт в Excel ---
@app.get("/export_excel")
def export_excel():
    response = requests.get(f"{SUPABASE_URL}/rest/v1/reports?select=*", headers=SUPABASE_HEADERS)
    data = response.json()
    if not data:
        return {"error": "Нет данных для экспорта"}

    df = pd.DataFrame(data)
    df.rename(columns={
        "id": "ID",
        "date_time": "Дата и время",
        "location": "Участок",
        "rig_number": "Номер буровой",
        "meterage": "Метраж",
        "pogon": "Погонометр",
        "note": "Примечание",
        "operator_name": "Ответственное лицо"
    }, inplace=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")

    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=svodka.xlsx"})
