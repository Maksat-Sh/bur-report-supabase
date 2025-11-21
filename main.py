from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

# -----------------------------
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# -----------------------------
DB_PATH = "database.db"

if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # таблица пользователей
    c.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
        """
    )

    # таблица отчётов буровиков
    c.execute(
        """
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime TEXT,
            area TEXT,
            rig_number TEXT,
            meter INTEGER,
            pogon INTEGER,
            operation TEXT,
            responsible TEXT,
            note TEXT
        )
        """
    )

    # начальные пользователи
    c.execute("INSERT INTO users (username, password, role) VALUES ('dispatcher', '1234', 'dispatcher')")
    c.execute("INSERT INTO users (username, password, role) VALUES ('bur1', '123', 'driller')")

    conn.commit()
    conn.close()

# -----------------------------
# Статические файлы и шаблоны
# -----------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -----------------------------
# Главная страница
# -----------------------------
@app.get("/")
def root():
    return RedirectResponse("/login")

# -----------------------------
# Страница логина
# -----------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

# -----------------------------
# Обработка логина
# -----------------------------
@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()

    if not row or row[1] != password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    role = row[2]

    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

# -----------------------------
# Интерфейс диспетчера
# -----------------------------
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM reports ORDER BY id DESC")
    reports = c.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )

# -----------------------------
# Форма буровика
# -----------------------------
@app.get("/burform", response_class=HTMLResponse)
def bur_form(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})

# -----------------------------
# Сохранение отчёта
# -----------------------------
@app.post("/burform", response_class=HTMLResponse)
def submit_report(
    request: Request,
    area: str = Form(...),
    rig_number: str = Form(...),
    meter: int = Form(...),
    pogon: int = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(None)
):

    from datetime import datetime

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reports (datetime, area, rig_number, meter, pogon, operation, responsible, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), area, rig_number, meter, pogon, operation, responsible, note)
    )
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        "burform.html",
        {"request": request, "success": "Отчёт сохранён"}
    )
