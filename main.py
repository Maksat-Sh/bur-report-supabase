from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
import hashlib
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

templates = Jinja2Templates(directory="templates")

# ======================
# БАЗА ДАННЫХ
# ======================
def get_db():
    return sqlite3.connect("db.sqlite3", check_same_thread=False)

db = get_db()
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    bur TEXT,
    area TEXT,
    meters REAL,
    pogonometer REAL,
    note TEXT
)
""")

db.commit()

# ======================
# ХЭШ
# ======================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ======================
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ (ОДИН РАЗ)
# ======================
def create_user(username, password, role):
    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role)
        )
        db.commit()
    except:
        pass

create_user("dispatcher", "123", "dispatcher")
create_user("bur1", "123", "bur")
create_user("bur2", "123", "bur")

# ======================
# АВТОРИЗАЦИЯ
# ======================
@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    cursor.execute(
        "SELECT id, password, role FROM users WHERE username = ?",
        (username,)
    )
    user = cursor.fetchone()

    if not user:
        return RedirectResponse("/login", status_code=302)

    user_id, password_hash, role = user

    if hash_password(password) != password_hash:
        return RedirectResponse("/login", status_code=302)

    request.session["user"] = {
        "id": user_id,
        "username": username,
        "role": role
    }

    if role == "dispatcher":
        return RedirectResponse("/reports", status_code=302)
    else:
        return RedirectResponse("/report/new", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ======================
# ФОРМА БУРОВИКА
# ======================
@app.get("/report/new", response_class=HTMLResponse)
def new_report(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "bur":
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "report_form.html",
        {"request": request, "user": user}
    )

@app.post("/report/new")
def save_report(
    request: Request,
    bur: str = Form(...),
    area: str = Form(...),
    meters: float = Form(...),
    pogonometer: float = Form(...),
    note: str = Form("")
):
    user = request.session.get("user")
    if not user or user["role"] != "bur":
        return RedirectResponse("/login")

    cursor.execute("""
        INSERT INTO reports (date, bur, area, meters, pogonometer, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        bur,
        area,
        meters,
        pogonometer,
        note
    ))
    db.commit()

    return RedirectResponse("/report/new", status_code=302)

# ======================
# ОТЧЁТЫ ДИСПЕТЧЕРА
# ======================
@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")

    cursor.execute("SELECT * FROM reports ORDER BY id DESC")
    reports = cursor.fetchall()

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "user": user,
            "reports": reports
        }
    )
