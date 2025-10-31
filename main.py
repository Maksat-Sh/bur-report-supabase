from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import asyncpg
import os
from datetime import datetime

app = FastAPI()

# Настройки путей
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# URL базы Supabase
DATABASE_URL = os.getenv("SUPABASE_DB_URL", "postgresql://postgres:password@db.supabase.co:5432/postgres")

# Авторизация (только диспетчер)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ADMIN_LOGIN = "dispatcher"
ADMIN_PASSWORD = "12345"

# ---------------- База данных ----------------
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            date_time TIMESTAMP,
            location TEXT,
            rig_number TEXT,
            meterage FLOAT,
            pogon FLOAT,
            note TEXT
        )
    """)
    await conn.close()

@app.on_event("startup")
async def startup():
    await init_db()

# ---------------- Маршруты ----------------
@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse("/dispatcher")

@app.get("/form", response_class=HTMLResponse)
async def show_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def submit_report(
    date_time: str = Form(...),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(...)
):
    conn = await get_connection()
    await conn.execute(
        "INSERT INTO reports (date_time, location, rig_number, meterage, pogon, note) VALUES ($1, $2, $3, $4, $5, $6)",
        datetime.fromisoformat(date_time), location, rig_number, meterage, pogon, note
    )
    await conn.close()
    return {"message": "Report submitted successfully"}

# ---------------- Вход диспетчера ----------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/dispatcher", status_code=303)
        response.set_cookie(key="auth", value="true")
        return response
    else:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    auth = request.cookies.get("auth")
    if auth != "true":
        return RedirectResponse("/login")

    conn = await get_connection()
    rows = await conn.fetch("SELECT * FROM reports ORDER BY id DESC")
    await conn.close()

    reports = [dict(r) for r in rows]
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})
