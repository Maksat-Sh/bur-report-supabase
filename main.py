from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import hashlib
import pandas as pd
from fastapi.responses import StreamingResponse
from io import BytesIO

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB = "reports.db"


# ----------------------- DB INIT -----------------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime TEXT,
        area TEXT,
        rig TEXT,
        meter INTEGER,
        pogon INTEGER,
        operation TEXT,
        responsible TEXT,
        note TEXT
    );
    """)

    conn.commit()

    # create default users if empty
    cur.execute("SELECT COUNT(*) FROM users;")
    if cur.fetchone()[0] == 0:
        print("Users table empty — creating default accounts")

        u1 = ("dispatcher", hashlib.sha256("1234".encode()).hexdigest(), "dispatcher")
        u2 = ("bur1", hashlib.sha256("123".encode()).hexdigest(), "bur")

        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", u1)
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", u2)
        conn.commit()

    conn.close()


init_db()


# ----------------------- AUTH -----------------------
def verify_user(username, password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username=? AND password=?", (username, hashed))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# ----------------------- ROUTES -----------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    role = verify_user(username, password)
    if not role:
        return RedirectResponse("/login", status_code=302)

    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)


@app.get("/logout")
async def logout():
    return RedirectResponse("/login")


# ----------------------- BUR FORM -----------------------
@app.get("/burform", response_class=HTMLResponse)
async def bur_form(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/submit_report")
async def submit_report(
        area: str = Form(...),
        rig: str = Form(...),
        meter: int = Form(...),
        pogon: int = Form(...),
        operation: str = Form(...),
        responsible: str = Form(...),
        note: str = Form(...)
):
    import datetime
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reports (datetime, area, rig, meter, pogon, operation, responsible, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (dt, area, rig, meter, pogon, operation, responsible, note))
    conn.commit()
    conn.close()

    return RedirectResponse("/burform", status_code=302)


# ----------------------- DISPATCHER PAGE -----------------------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": rows})


# ----------------------- USERS PAGE -----------------------
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT username, role FROM users")
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse("users.html", {"request": request, "users": rows})


# ----------------------- EXPORT EXCEL -----------------------
@app.get("/export_excel")
async def export_excel():

    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM reports", conn)
    conn.close()

    output = BytesIO()
    df.to_excel(output, index=False, sheet_name="Отчёты")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )
