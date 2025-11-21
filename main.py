from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime
import io
from openpyxl import Workbook

# bcrypt hashing
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
load_dotenv()
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------------------------------------------
# SUPABASE HELPERS
# -------------------------------------------------------
async def supabase_get(table: str, params: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def supabase_post(table: str, payload: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
       "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


# -------------------------------------------------------
# AUTH HELPERS
# -------------------------------------------------------
def get_current_user(request: Request):
    return request.session.get("user")


# -------------------------------------------------------
# ROOT + LOGIN
# -------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/report-form")
async def report_form(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("report_form.html", {"request": request, "user": user})




@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await supabase_get("users", f"?select=*&username=eq.{username}")

    if not users:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    user = users[0]

    # Проверка bcrypt
    if not pwd_context.verify(password, user.get("password_hash", "")):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    # ⬅ Если пароль верный — сохраняем юзера
    request.session["user"] = user

    # Переход по роли
    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    if user["role"] == "driller":
        return RedirectResponse("/report-form", status_code=302)

    return RedirectResponse("/", status_code=302)




@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -------------------------------------------------------
# REPORT FORM FOR DRILLERS
# -------------------------------------------------------
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/submit")
async def submit_report(
        date: str = Form(...),
        time: str = Form(...),
        site: str = Form(...),
        rig_number: str = Form(...),
        meterage: str = Form(...),
        pogon: str = Form(...),
        note: str = Form("")
):
    payload = {
        "date": date,
        "time": time,
        "section": site,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogonometr": pogon,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    await supabase_post("reports", payload)

    return {"message": "Report submitted successfully"}


# -------------------------------------------------------
# DISPATCHER PAGE
# -------------------------------------------------------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    params = "?select=*&order=created_at.desc"
    if section:
        params = f"?select=*&order=created_at.desc&section=eq.{section}"

    reports = await supabase_get("reports", params)

    sites = ['', 'Хорасан', 'Заречное', 'Карамурын', 'Ирколь', 'Степногорск']

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": user, "reports": reports, "sites": sites, "selected_site": section or ""}
    )


# -------------------------------------------------------
# EXPORT EXCEL
# -------------------------------------------------------
@app.get("/export_excel")
async def export_excel(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    params = "?select=*&order=created_at.desc"
    if section:
        params = f"?select=*&order=created_at.desc&section=eq.{section}"

    reports = await supabase_get("reports", params)

    wb = Workbook()
    ws = wb.active
    ws.title = "reports"

    ws.append([
        "ID", "Дата UTC", "Участок", "Номер агрегата", "Метраж", "Погонометр",
        "Операция", "Автор", "Примечание"
    ])

    for r in reports:
        created = r.get("created_at") or r.get("timestamp") or ""
        ws.append([
            r.get("id"),
            created,
            r.get("section") or r.get("location"),
            r.get("rig_number"),
            r.get("meterage"),
            r.get("pogonometr"),
            r.get("operation_type") or r.get("operation"),
            r.get("operator_name"),
            r.get("note") or ""
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'}
    )


# -------------------------------------------------------
# USERS PAGE
# -------------------------------------------------------
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")

    users = await supabase_get("users", "?select=*")
    sites = ['Хорасан', 'Заречное', 'Карамурын', 'Ирколь', 'Степногорск']

    return templates.TemplateResponse(
        "users.html",
        {"request": request, "user": user, "users": users, "sites": sites}
    )


# -------------------------------------------------------
# CREATE USER
# -------------------------------------------------------
@app.post("/create_user")
async def create_user(
        request: Request,
        username: str = Form(...),
        full_name: str = Form(""),
        password: str = Form(...),
        role: str = Form(...),
        location: str = Form(None)
):
    admin = get_current_user(request)
    if not admin or admin.get("role") != "dispatcher":
        return RedirectResponse("/login")

    payload = {
        "username": username,
        "full_name": full_name,
        "fio": full_name,
        "password": password,
        "password_hash": pwd_context.hash(password),  # bcrypt
        "role": role,
        "location": location,
        "created_at": datetime.utcnow().isoformat()
    }

    await supabase_post("users", payload)

    return RedirectResponse("/users", status_code=303)


# -------------------------------------------------------
# PING
# -------------------------------------------------------
@app.get("/ping")
def ping():
    return {"status": "ok"}
