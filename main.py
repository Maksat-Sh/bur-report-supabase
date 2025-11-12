from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import io
from openpyxl import Workbook
import hashlib
from passlib.context import CryptContext

# ==========================================
# Настройки
# ==========================================
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SESSION_SECRET = os.getenv("SESSION_SECRET", "supersecret")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


# ==========================================
# Вспомогательные функции
# ==========================================
async def supabase_get_reports():
    async with httpx.AsyncClient() as client:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = await client.get(f"{SUPABASE_URL}/rest/v1/reports?select=*", headers=headers)
        return r.json()

async def supabase_insert_report(data):
    async with httpx.AsyncClient() as client:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        await client.post(f"{SUPABASE_URL}/rest/v1/reports", headers=headers, json=data)

# ==========================================
# Страницы
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login")
    reports = await supabase_get_reports()
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    ADMIN_USER = os.getenv("ADMIN_USER", "dispatcher")
    ADMIN_PASS_HASH = os.getenv("ADMIN_PASS_HASH")
    if not ADMIN_PASS_HASH:
        ADMIN_PASS_HASH = pwd_context.hash("12345")

    if username == ADMIN_USER and pwd_context.verify(password, ADMIN_PASS_HASH):
        request.session["logged_in"] = True
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ==========================================
# API: приём сводки от буровика
# ==========================================
@app.post("/submit")
async def submit_report(
    section: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form("")
):
    data = {
        "section": section,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "datetime": datetime.now(timezone.utc).isoformat()
    }
    await supabase_insert_report(data)
    return {"message": "Report submitted successfully"}

# ==========================================
# API: экспорт в Excel
# ==========================================
@app.get("/export_excel")
async def export_excel(request: Request):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login")
    reports = await supabase_get_reports()

    wb = Workbook()
    ws = wb.active
    ws.title = "Сводки"

    ws.append(["ID", "Участок", "Номер буровой", "Метраж", "Погонометр", "Примечание", "Дата/время"])
    for r in reports:
        ws.append([
            r.get("id", ""),
            r.get("section", ""),
            r.get("rig_number", ""),
            r.get("meterage", ""),
            r.get("pogon", ""),
            r.get("note", ""),
            r.get("datetime", "")
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )

# ==========================================
# Тест
# ==========================================
@app.get("/ping")
def ping():
    return {"status": "ok"}
