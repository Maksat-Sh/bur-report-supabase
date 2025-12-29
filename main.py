from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
from datetime import datetime
from passlib.context import CryptContext

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SUPER_SECRET_KEY")

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------- DB --------------------
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

# -------------------- USERS INIT --------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def init_users():
    users = [
        ("dispatcher", hash_password("123"), "dispatcher"),
        ("bur1", hash_password("123"), "bur"),
        ("bur2", hash_password("123"), "bur"),
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

# -------------------- LOGIN --------------------
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
        "SELECT password, role FROM users WHERE username=?",
        (username,)
    )
    user = cursor.fetchone()

    if not user or not verify_password(password, user[0]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    request.session["user"] = username
    request.session["role"] = user[1]

    if user[1] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
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
    meters: float = Form(...),
    pogonometr: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form("")
):
    if request.session.get("role") != "bur":
        return RedirectResponse("/login", status_code=302)

    bur = request.session["user"]
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO reports
        (date, bur, area, meters, pogonometr, operation, responsible, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (date, bur, area, meters, pogonometr, operation, responsible, note))

    conn.commit()
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

# -------------------- API --------------------
@app.get("/reports")
def get_reports(request: Request):
    if request.session.get("role") != "dispatcher":
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    cursor.execute("""
        SELECT id, date, bur, area, meters, pogonometr, operation, responsible, note
        FROM reports ORDER BY id DESC
    """)
    rows = cursor.fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "date": r[1],
            "bur": r[2],
            "area": r[3],
            "meters": r[4],
            "pogonometr": r[5],
            "operation": r[6],
            "responsible": r[7],
            "note": r[8]
        })

    return result
