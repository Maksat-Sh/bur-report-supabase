from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from supabase import create_client, Client
import pandas as pd
import io
from starlette.middleware.sessions import SessionMiddleware
import os
from fastapi.middleware.cors import CORSMiddleware

# --- Настройки Supabase ---
SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"  # вставь свой URL
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92a2Zha3B3Z3ZycGJuamJya3phIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3OTUxMjMsImV4cCI6MjA3MjM3MTEyM30.8vsXFCdhgyTi6yJW1DXJOyvjuqoWJmivGCNYFN5dNv8"         # вставь свой service_role
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SUPABASE_URL = os.getenv("SUPABASE_URL") or "postgresql://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8iur433s73btijog-a/report_oag9"
engine = create_engine(
    SUPABASE_URL,
    connect_args={"options": "-c client_encoding=utf8"},
    echo=False,
    encoding="utf-8"
)
app = FastAPI()
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
# --- Настройки сессий ---
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
# Разрешаем CORS (чтобы фронт мог подключаться)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- Подключаем статику и шаблоны ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- Главная ----------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login_dispatcher")


# ---------- Авторизация диспетчера ----------
@app.get("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher(request: Request):
    return templates.TemplateResponse("login_dispatcher.html", {"request": request})


@app.post("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "1234":
        request.session["logged_in"] = True
        return RedirectResponse("/dispatcher", status_code=303)
    return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин или пароль"})


# ---------- Страница диспетчера ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login_dispatcher")

    try:
        response = supabase.table("reports").select("*").execute()
        reports = response.data or []
    except Exception as e:
        reports = []
        print("Ошибка при загрузке данных:", e)

    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})


# ---------- Экспорт в Excel ----------
@app.get("/export_excel")
async def export_excel():
    try:
        response = supabase.table("reports").select("*").execute()
        data = response.data or []

        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Отчеты")

        output.seek(0)
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="reports.xlsx",
        )
    except Exception as e:
        return {"error": str(e)}


# ---------- Форма буровика ----------
@app.get("/login_worker", response_class=HTMLResponse)
async def login_worker(request: Request):
    return templates.TemplateResponse("worker_form.html", {"request": request})


# ---------- Отправка отчёта буровиком ----------
@app.post("/submit_worker_report")
async def submit_worker_report(
    date: str = Form(...),
    time: str = Form(...),
    location: str = Form(...),
    drill_number: str = Form(...),
    meterage: float = Form(...),
    footage: float = Form(...),
    note: str = Form(None)
):
    try:
        data = {
            "date": date,
            "time": time,
            "location": location,
            "drill_number": drill_number,
            "meterage": meterage,
            "footage": footage,
            "note": note
        }
        supabase.table("reports").insert(data).execute()
        return {"message": "Отчёт успешно сохранён!"}
    except Exception as e:
        return {"message": f"Ошибка при сохранении: {str(e)}"}


# ---------- Выход диспетчера ----------
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login_dispatcher", status_code=303)
