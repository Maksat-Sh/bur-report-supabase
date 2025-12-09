from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import datetime
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def db():
    return await asyncpg.connect(DATABASE_URL)

# ---------------------------
# helper for authorization
# ---------------------------
async def current_user(request: Request):
    return request.session.get("user")


# ---------------------------
# HOME → login
# ---------------------------
@app.get("/")
async def home():
    return RedirectResponse("/login")


# ---------------------------
# LOGIN
# ---------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = await db()

    user = await conn.fetchrow("SELECT * FROM users WHERE username=$1", username)
    await conn.close()

    if not user:
        return RedirectResponse("/login?error=1", status_code=302)

    if not pwd_context.verify(password, user["password_hash"]):
        return RedirectResponse("/login?error=1", status_code=302)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"]
    }
    return RedirectResponse("/dispatcher", status_code=302)


# ---------------------------
# LOGOUT
# ---------------------------
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ---------------------------
# dispatcher
# ---------------------------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    user = await current_user(request)

    if not user:
        return RedirectResponse("/login")

    if user["role"] != "dispatcher":
        return RedirectResponse("/burform")

    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/api/reports")
async def get_reports(request: Request):
    user = await current_user(request)
    if not user:
        return []

    conn = await db()
    rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at DESC")
    await conn.close()

    return [dict(r) for r in rows]


# ---------------------------
# burform
# ---------------------------
@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/burform")
async def burform_submit(
        section: str = Form(...),
        bur: str = Form(...),
        bur_no: str = Form(...),
        location: str = Form(...),
        footage: int = Form(...),
        pogonometr: int = Form(...),
        operation_type: str = Form(...),
        operation: str = Form(...),
        note: str = Form("")
):
    conn = await db()

    await conn.execute("""
        INSERT INTO reports (section,bur,bur_no,location,footage,pogonometr,
        operation_type,operation,note,created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,now())
    """,
        section,bur,bur_no,location,footage,pogonometr,operation_type,operation,note
    )

    await conn.close()
    return RedirectResponse("/burform?ok=1", status_code=302)


# ---------------------------
# dispatcher adds users
# ---------------------------
@app.post("/create_user")
async def create_user(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        full_name: str = Form(""),
        role: str = Form(...)
):
    user = await current_user(request)
    if not user or user["role"] != "dispatcher":
        return {"error": "forbidden"}

    conn = await db()
    await conn.execute("""
        INSERT INTO users(username, full_name, password_hash, role, created_at)
        VALUES($1,$2,$3,$4,now())
    """,
    username, full_name, pwd_context.hash(password), role)

    await conn.close()
    return RedirectResponse("/dispatcher?user_added=1", status_code=302)
