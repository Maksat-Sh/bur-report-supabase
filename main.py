from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import psycopg2
import os
from datetime import datetime

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_123"
)

templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://USER:PASSWORD@HOST:5432/DBNAME"
)

def get_db():
    return psycopg2.connect(DATABASE_URL)

# ---------- AUTH ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), request: Request = None):
    if username == "dispatcher" and password == "1234":
        request.session["user"] = "dispatcher"
        return RedirectResponse("/dispatcher", status_code=302)

    if username == "bur" and password == "1234":
        request.session["user"] = "bur"
        return RedirectResponse("/bur", status_code=302)

    return RedirectResponse("/login", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

def require_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise Exception("Unauthorized")
    return user

# ---------- BUR ----------
@app.get("/bur", response_class=HTMLResponse)
def bur_page(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(
        "bur.html",
        {"request": request, "user": user}
    )

@app.post("/bur")
def submit_report(
    request: Request,
    area: str = Form(...),
    rig_number: str = Form(...),
    meters: float = Form(...),
    pogonometr: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form("")
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO reports
        (bur, section, bur_no, footage, pogonometr, operation_type, person, note, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        "bur",
        area,
        rig_number,
        meters,
        pogonometr,
        operation,
        responsible,
        note,
        datetime.utcnow()
    ))

    conn.commit()
    cur.close()
    conn.close()

    return RedirectResponse("/bur", status_code=302)

# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request, user=Depends(require_user)):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT section, bur_no, footage, pogonometr, operation_type, person, note, created_at
        FROM reports
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": rows}
    )
