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
from passlib.context import CryptContext
import psycopg2

def get_all_reports():
    conn = psycopg2.connect(
        "postgresql://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8iur433s73btijog-a/report_oag9"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date_time, location, rig_number, footage, pogonometr, note
        FROM reports
        ORDER BY date_time DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

# ==========================================
# Настройки
# ==========================================
load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
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


async def get_stored_password_hash():
    """Получить хеш пароля из таблицы settings"""
    async with httpx.AsyncClient() as client:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/settings?select=value&key=eq.admin_pass_hash"
        r = await client.get(url, headers=headers)
        data = r.json()
        if data:
            return data[0]["value"]
        return None


async def set_stored_password_hash(new_hash: str):
    """Сохранить новый хеш пароля"""
    async with httpx.AsyncClient() as client:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        # Проверяем, есть ли уже запись
        check = await client.get(f"{SUPABASE_URL}/rest/v1/settings?key=eq.admin_pass_hash", headers=headers)
        if check.json():
            await client.patch(f"{SUPABASE_URL}/rest/v1/settings?key=eq.admin_pass_hash", headers=headers, json={"value": new_hash})
        else:
            await client.post(f"{SUPABASE_URL}/rest/v1/settings", headers=headers, json={"key": "admin_pass_hash", "value": new_hash})


# ==========================================
# Страницы
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    reports = get_all_reports()
    user = {"username": "dispatcher"}  # фиктивный пользователь для шаблона
    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports,
        "user": user
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    ADMIN_USER = os.getenv("ADMIN_USER", "dispatcher")

    stored_hash = await get_stored_password_hash()
    if not stored_hash:
        # если нет — используем дефолтный
        stored_hash = pwd_context.hash("dispatch123")
        await set_stored_password_hash(stored_hash)

    if username == ADMIN_USER and pwd_context.verify(password, stored_hash):
        request.session["logged_in"] = True
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ==========================================
# Смена пароля
# ==========================================
@app.get("/change_password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login")
    return templates.TemplateResponse("change_password.html", {"request": request, "message": None, "error": None})


@app.post("/change_password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...)
):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login")

    stored_hash = await get_stored_password_hash()
    if not pwd_context.verify(old_password, stored_hash):
        return templates.TemplateResponse("change_password.html", {"request": request, "error": "Старый пароль неверный", "message": None})

    new_hash = pwd_context.hash(new_password)
    await set_stored_password_hash(new_hash)
    return templates.TemplateResponse("change_password.html", {"request": request, "error": None, "message": "Пароль успешно изменён!"})


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
