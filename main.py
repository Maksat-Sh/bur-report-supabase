from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

templates = Jinja2Templates(directory="templates")

# -------------------
# НАСТРОЙКИ
# -------------------

USERS = {
    "dispatcher": {"password": "123", "role": "dispatcher"},
    "bur1": {"password": "123", "role": "bur"},
    "bur2": {"password": "123", "role": "bur"},
}

# -------------------
# БАЗА
# -------------------

def get_db():
    conn = sqlite3.connect("reports.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            bur TEXT,
            area TEXT,
            meters REAL,
            pogonometr REAL,
            note TEXT
        )
    """)
    db.commit()
    db.close()

init_db()

# -------------------
# AUTH
# -------------------

def get_current_user(request: Request):
    return request.session.get("user")

# -------------------
# ROUTES
# -------------------

@app.get("/")
def root():
    return RedirectResponse("/login")

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    user = USERS.get(username)
    if not user or user["password"] != password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    request.session["user"] = {"username": username, "role": user["role"]}

    if user["role"] == "dispatcher":
        return RedirectResponse("/reports", status_code=302)
    else:
        return RedirectResponse("/bur", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# -------------------
# БУРОВИК
# -------------------

@app.get("/bur")
def bur_form(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "bur":
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "bur_form.html",
        {"request": request, "user": user}
    )

@app.post("/bur")
def bur_submit(
    request: Request,
    area: str = Form(...),
    meters: float = Form(...),
    pogonometr: float = Form(...),
    note: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    db = get_db()
    db.execute("""
        INSERT INTO reports (date, bur, area, meters, pogonometr, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        user["username"],
        area,
        meters,
        pogonometr,
        note
    ))
    db.commit()
    db.close()

    return RedirectResponse("/bur", status_code=302)

# -------------------
# ДИСПЕТЧЕР
# -------------------

@app.get("/reports")
def reports(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")

    db = get_db()
    rows = db.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
    db.close()

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "user": user,
            "reports": rows
        }
    )
