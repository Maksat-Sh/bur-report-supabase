from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SUPER_SECRET_KEY")

templates = Jinja2Templates(directory="templates")

# ================== DATABASE ==================
conn = sqlite3.connect("db.sqlite3", check_same_thread=False)
cursor = conn.cursor()

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
    pogonometr REAL,
    operation TEXT,
    responsible TEXT,
    note TEXT
)
""")

conn.commit()

# ================== INIT USERS ==================
def init_users():
    users = [
        ("dispatcher", "123", "dispatcher"),
        ("bur1", "123", "bur"),
        ("bur2", "123", "bur"),
    ]
    for u in users:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", u
            )
        except:
            pass
    conn.commit()

init_users()

# ================== LOGIN ==================
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
        "SELECT role FROM users WHERE username=? AND password=?",
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

# ================== LOGOUT ==================
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ================== BUR ==================
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
    rig_number: str = Form(...),
    meters: float = Form(...),
    pogonometr: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form("")
):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login", status_code=302)

    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    bur = request.session.get("user")

    cursor.execute("""
        INSERT INTO reports
        (date, bur, area, meters, pogonometr, operation, responsible, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (date, bur, area, meters, pogonometr, operation, responsible, note))

    conn.commit()
    return RedirectResponse("/bur", status_code=302)

# ================== DISPATCHER ==================
@app.get("/dispatcher")
def dispatcher_page(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    cursor.execute("""
        SELECT id, date, bur, area, meters, pogonometr, operation, responsible, note
        FROM reports
        ORDER BY id DESC
    """)
    reports = cursor.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )

# ================== API ==================
@app.get("/reports")
def get_reports(request: Request):
    if request.session.get("role") != "dispatcher":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    cursor.execute("SELECT * FROM reports ORDER BY id DESC")
    return cursor.fetchall()

@app.get("/db-check")
def db_check():
    cursor.execute("SELECT COUNT(*) FROM reports")
    return {"reports_count": cursor.fetchone()[0]}
