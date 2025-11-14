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
from passlib.context import CryptContext

# === Настройки ===
load_dotenv()
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = "reports"

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# === Вспомогательные функции ===
async def supabase_request(method: str, endpoint: str = "", data=None, params=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}{endpoint}"
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=data, params=params)
    response.raise_for_status()
    return response.json() if response.text else None


# === Аутентификация ===
ADMIN_LOGIN = "dispatcher"
ADMIN_PASSWORD_HASH = pwd_context.hash("dispatch123")


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_LOGIN and pwd_context.verify(password, ADMIN_PASSWORD_HASH):
        request.session["user"] = username
        return RedirectResponse("/dispatcher", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# === Отчёт буровика ===
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/submit")
async def submit_report(
    request: Request,
    date: str = Form(...),
    time: str = Form(...),
    site: str = Form(...),
    rig_number: str = Form(...),
    meterage: str = Form(...),
    pogon: str = Form(...),
    note: str = Form(""),
):
    data = {
        "date": date,
        "time": time,
        "site": site,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }
    await supabase_request("POST", "", data=[data])
    return {"message": "Report submitted successfully"}


# === Интерфейс диспетчера ===
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    reports = await supabase_request("GET", "", params={"select": "*", "order": "id.desc"})
    user = {"username": "dispatch"}
    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports, "user": user}
    )


    reports = await supabase_request("GET", "", params={"select": "*", "order": "id.desc"})
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})


# === Экспорт в Excel ===
@app.get("/export_excel")
async def export_excel(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/login")

    reports = await supabase_request("GET", "", params={"select": "*"})
    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка"

    headers = ["ID", "Дата", "Время", "Участок", "Буровая", "Метраж", "Погонометр", "Примечание"]
    ws.append(headers)

    for r in reports:
        ws.append([
            r.get("id"),
            r.get("date"),
            r.get("time"),
            r.get("site"),
            r.get("rig_number"),
            r.get("meterage"),
            r.get("pogon"),
            r.get("note"),
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=reports.xlsx"},
    )
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    # Проверяем, что диспетчер вошёл
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/login", status_code=302)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, login FROM auth.users ORDER BY id ASC")
            users = cur.fetchall()
    except Exception as e:
        print("Ошибка при получении пользователей:", e)
        users = []

    html = """
    <html>
    <head>
        <title>Пользователи</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <h2>Список пользователей</h2>
        <table border="1" cellpadding="8">
            <tr>
                <th>ID</th>
                <th>Логин</th>
            </tr>
    """

    for user in users:
        html += f"""
            <tr>
                <td>{user[0]}</td>
                <td>{user[1]}</td>
            </tr>
        """

    html += """
        </table>

        <br>
        <a href="/dispatcher">
            <button>⬅ Назад</button>
        </a>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
