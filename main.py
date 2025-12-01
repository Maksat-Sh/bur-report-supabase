import os
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from datetime import datetime
from openpyxl import Workbook
from io import BytesIO

# -------------------------
#   APP INIT
# -------------------------

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -------------------------
#   SUPABASE HELPERS
# -------------------------

def sb_select(table, filters=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if filters:
        url += f"?{filters}"

    r = requests.get(url, headers={
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
    })
    print("SELECT:", url, r.status_code, r.text)
    return r.json() if r.status_code == 200 else []


def sb_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    r = requests.post(url, json=data, headers={
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    })
    print("INSERT:", url, r.status_code, r.text)
    return r.json()


# -------------------------
#   ROOT → LOGIN
# -------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request, error: int = 0):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form["username"]
    password = form["password"]

    # Запрос в Supabase
    url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    r = requests.get(url, headers=headers)
    print("SELECT:", url, r.status_code, r.text)

    if r.status_code != 200:
        return RedirectResponse("/login?error=1", status_code=302)

    data = r.json()
    if not data:
        return RedirectResponse("/login?error=1", status_code=302)

    user = data[0]

    # --- ВАЖНО: проверяем именно password_hash ---
    password_hash = user.get("password_hash")

    if not password_hash:
        return RedirectResponse("/login?error=1", status_code=302)

    # bcrypt verify
    if not pwd_context.verify(password, password_hash):
        return RedirectResponse("/login?error=1", status_code=302)

    # Успешный вход — создаём сессию
    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"]
    }

    # Перенаправление по роли
    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)

async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    users = sb_select("users", f"username=eq.{username}")

    if not users:
        return RedirectResponse("/login?error=1", status_code=302)

    user = users[0]

    if not pwd_context.verify(password, user["password_hash"]):
        return RedirectResponse("/login?error=1", status_code=302)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "section": user.get("section", "")
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/burform", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -------------------------
#   BUR FORM
# -------------------------

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "bur":
        return RedirectResponse("/login")

    return templates.TemplateResponse("burform.html", {"request": request, "user": user})


@app.post("/submit_report")
async def submit_report(
        request: Request,
        operation_type: str = Form(...),
        operation: str = Form(...),
        footage: int = Form(...),
        pogonometr: int = Form(...),
        note: str = Form("")
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    data = {
        "created_at": datetime.utcnow().isoformat(),
        "operation_type": operation_type,
        "operation": operation,
        "footage": footage,
        "pogonometr": pogonometr,
        "note": note,
        "section": user["section"],
        "bur": user["full_name"],
        "bur_no": user["username"]
    }

    sb_insert("reports", data)

    return RedirectResponse("/burform?success=1", status_code=302)


# -------------------------
#   DISPATCHER PAGE
# -------------------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request, section: str = ""):
    user = request.session.get("user")
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")

    if section:
        reports = sb_select("reports", f"section=eq.{section}&order=created_at.desc")
    else:
        reports = sb_select("reports", "order=created_at.desc")

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports,
        "selected_section": section
    })


# -------------------------
#   EXPORT EXCEL
# -------------------------

@app.get("/export_excel")
async def export_excel():
    reports = sb_select("reports", "order=created_at.desc")

    wb = Workbook()
    ws = wb.active
    ws.append(["Дата", "Участок", "Буровик", "Агрегат", "Метраж", "Погонометр", "Операция", "Тип", "Примечание"])

    for r in reports:
        ws.append([
            r["created_at"],
            r["section"],
            r["bur"],
            r["bur_no"],
            r["footage"],
            r["pogonometr"],
            r["operation"],
            r["operation_type"],
            r["note"],
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reports.xlsx"}
    )
