from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import psycopg2
import os
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SECRET_KEY_123")

templates = Jinja2Templates(directory="templates")

# -------------------- DB --------------------
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

# -------------------- TABLES --------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    date TEXT,
    bur TEXT,
    area TEXT,
    meters INTEGER,
    pogonometr INTEGER,
    note TEXT
)
""")

# -------------------- USERS INIT --------------------
def init_users():
    users = [
        ("dispatcher", "123", "dispatcher"),
        ("bur1", "123", "bur"),
        ("bur2", "123", "bur"),
    ]
    for u in users:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                u
            )
        except:
            pass

init_users()

# -------------------- LOGIN --------------------
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
    cursor.execute(
        "SELECT role FROM users WHERE username=%s AND password=%s",
        (username, password)
    )
    user = cursor.fetchone()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    request.session["user"] = username
    request.session["role"] = user[0]

    if user[0] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/bur", status_code=302)

# -------------------- LOGOUT --------------------
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# -------------------- BUR --------------------
@app.get("/bur")
def bur_page(request: Request):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "bur.html",
        {"request": request, "user": request.session["user"]}
    )

@app.post("/bur")
def send_report(
    request: Request,
    area: str = Form(...),
    meters: int = Form(...),
    pogonometr: int = Form(...),
    note: str = Form("")
):
    bur = request.session.get("user")
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO reports (date, bur, area, meters, pogonometr, note)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (date, bur, area, meters, pogonometr, note))

    return RedirectResponse("/bur", status_code=302)

# -------------------- DISPATCHER --------------------
@app.get("/dispatcher")
def dispatcher_page(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    cursor.execute("SELECT * FROM reports ORDER BY id DESC")
    reports = cursor.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )
