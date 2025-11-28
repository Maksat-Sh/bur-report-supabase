from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import io
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

import os
from passlib.context import CryptContext

# -----------------------------
# ИНИЦИАЛИЗАЦИЯ
# -----------------------------
app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="supersecretkey123")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# -----------------------------
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------
def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)


def require_login(session):
    if "user" not in session:
        return False
    return True


# -----------------------------
#  LOGIN PAGE
# -----------------------------
@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: int = 0):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = supabase.table("users").select("*").eq("username", username).execute()

    if len(user.data) == 0:
        return RedirectResponse("/login?error=1", status_code=302)

    user = user.data[0]

    if not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login?error=1", status_code=302)

    # Save session
    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "section": user.get("section", "")
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)


@app.get("/logout", response_class=RedirectResponse)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -----------------------------
#     ФОРМА БУРОВИКА
# -----------------------------
@app.get("/burform", response_class=HTMLResponse)
def burform(request: Request):
    if not require_login(request.session):
        return RedirectResponse("/login")

    user = request.session["user"]

    return templates.TemplateResponse("burform.html", {
        "request": request,
        "full_name": user["full_name"],  # буровика ФИО
        "section": user["section"]       # участок буровика
    })


@app.post("/submit_report")
def submit_report(
        request: Request,
        operation_type: str = Form(...),
        operation: str = Form(...),
        footage: int = Form(...),
        pogonometr: int = Form(...),
        note: str = Form(""),
):
    if not require_login(request.session):
        return RedirectResponse("/login")

    user = request.session["user"]

    supabase.table("reports").insert({
        "created_at": datetime.utcnow().isoformat(),
        "bur": user["full_name"],
        "location": user["section"],
        "operation_type": operation_type,
        "operation": operation,
        "footage": footage,
        "pogonometr": pogonometr,
        "note": note,
        "section": user["section"],
        "bur_no": user["username"]
    }).execute()

    return RedirectResponse("/burform?success=1", status_code=302)


# -----------------------------
#     ДИСПЕТЧЕРСКАЯ
# -----------------------------
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request, section: str = None):
    if not require_login(request.session):
        return RedirectResponse("/login")

    user = request.session["user"]
    if user["role"] != "dispatcher":
        return RedirectResponse("/login")

    query = supabase.table("reports").select("*")

    if section:
        query = query.eq("section", section)

    reports = query.order("id", desc=True).execute().data

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports,
        "section_filter": section
    })


# -----------------------------
#     ЭКСПОРТ В EXCEL
# -----------------------------
@app.get("/export_excel")
def export_excel(request: Request):
    if not require_login(request.session):
        return RedirectResponse("/login")

    user = request.session["user"]
    if user["role"] != "dispatcher":
        return RedirectResponse("/login")

    data = supabase.table("reports").select("*").execute().data
    df = pd.DataFrame(data)

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )


# -----------------------------
#     СТРАНИЦА ПОЛЬЗОВАТЕЛЕЙ
# -----------------------------
@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    if not require_login(request.session):
        return RedirectResponse("/login")

    user = request.session["user"]
    if user["role"] != "dispatcher":
        return RedirectResponse("/login")

    users = supabase.table("users").select("*").execute().data

    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users
    })


@app.post("/users/create")
def create_user(
        username: str = Form(...),
        password: str = Form(...),
        full_name: str = Form(...),
        section: str = Form(...),
        role: str = Form(...)
):
    supabase.table("users").insert({
        "username": username,
        "password_hash": hash_password(password),
        "full_name": full_name,
        "section": section,
        "role": role,
        "created_at": datetime.utcnow().isoformat()
    }).execute()

    return RedirectResponse("/users", status_code=302)
