import os
import io
import requests
import pandas as pd
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime
from utils.auth import hash_password, verify_password

load_dotenv()

SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")  # set this in your Render env or .env
SESSION_KEY = os.getenv("SESSION_KEY", "change_this_session_secret")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL missing")
if not SUPABASE_API_KEY:
    print("WARNING: SUPABASE_API_KEY not set. Set SUPABASE_API_KEY in environment for DB access.")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY or "",
    "Authorization": f"Bearer {SUPABASE_API_KEY or ''}",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_KEY)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- simple in-memory users fallback (used only if Supabase create/list fails) ---
FALLBACK_USERS = {
    "admin": { "password_hash": hash_password("admin123"), "role": "admin", "full_name": "Администратор", "location": "Степногорск", "unit": "1" },
    "bur1": { "password_hash": hash_password("123"), "role": "driller", "full_name": "Бурильщик 1", "location": "Хорасан", "unit": "5" },
}

def supabase_get(path, params=None):
    if not SUPABASE_API_KEY:
        return None
    url = SUPABASE_URL.rstrip('/') + path
    r = requests.get(url, headers=SUPABASE_HEADERS, params=params, timeout=10)
    return r

def supabase_post(path, json_body):
    if not SUPABASE_API_KEY:
        return None
    url = SUPABASE_URL.rstrip('/') + path
    r = requests.post(url, headers=SUPABASE_HEADERS, json=json_body, timeout=10)
    return r

# --- Routes ---
@app.get('/', response_class=HTMLResponse)
def root(request: Request):
    user = request.session.get("user")
    if user:
        role = user.get("role")
        if role in ("dispatcher", "admin"):
            return RedirectResponse("/dispatcher")
        return RedirectResponse("/form")
    return RedirectResponse("/login")

@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", { "request": request })

@app.post('/login')
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Try Supabase first
    if SUPABASE_API_KEY:
        r = supabase_get('/rest/v1/users?select=*&username=eq.' + username)
        if r and r.status_code == 200:
            rows = r.json()
            if rows:
                u = rows[0]
                if verify_password(password, u.get("password_hash") or ""):
                    request.session["user"] = {
                        "username": username,
                        "role": u.get("role"),
                        "full_name": u.get("full_name") or u.get("fio") or username,
                        "location": u.get("location"),
                        "unit": u.get("unit")
                    }
                    return RedirectResponse("/", status_code=303)
    # Fallback
    fu = FALLBACK_USERS.get(username)
    if fu and verify_password(password, fu["password_hash"]):
        request.session["user"] = {
            "username": username,
            "role": fu["role"],
            "full_name": fu["full_name"],
            "location": fu["location"],
            "unit": fu["unit"]
        }
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", { "request": request, "error": "Неверный логин или пароль" })

@app.get('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get('/form', response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") == "dispatcher":
        return RedirectResponse("/login")
    # Provide lists
    sections = ["Карамурын","Ирколь","Хорасан","Заречное","Степногорск"]
    return templates.TemplateResponse("form.html", {
        "request": request,
        "user": user,
        "sections": sections
    })

@app.post('/submit')
def submit(request: Request,
           meterage: float = Form(...),
           pogon: float = Form(...),
           operation: str = Form(""),
           note: str = Form(""),
          ):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    now = datetime.now().astimezone().isoformat()
    report = {
        "date_time": now,
        "location": user.get("location"),
        "rig_number": user.get("unit"),
        "meterage": meterage,
        "pogon": pogon,
        "operation": operation,
        "operator_name": user.get("full_name"),
        "note": note,
        "created_at": now
    }
    if SUPABASE_API_KEY:
        r = supabase_post('/rest/v1/reports', report)
        if not r or r.status_code not in (200,201):
            raise HTTPException(status_code=500, detail=r.text if r else "Supabase not configured")
        return { "message": "Сводка успешно отправлена!" }
    else:
        # fallback - no DB
        return { "message": "Сводка принята (локально)" }

@app.get('/dispatcher', response_class=HTMLResponse)
def dispatcher(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher", "admin"):
        return RedirectResponse("/login")
    reports = []
    users = []
    if SUPABASE_API_KEY:
        rr = supabase_get('/rest/v1/reports?select=*')
        if rr and rr.status_code == 200:
            try:
                reports = rr.json()
            except:
                reports = []
        ur = supabase_get('/rest/v1/users?select=id,username,role,full_name,location,unit,created_at')
        if ur and ur.status_code == 200:
            users = ur.json()
    return templates.TemplateResponse("dispatcher.html", { "request": request, "user": user, "reports": reports, "users": users })

@app.get('/export_excel')
def export_excel():
    if SUPABASE_API_KEY:
        r = supabase_get('/rest/v1/reports?select=*')
        if not r or r.status_code != 200:
            raise HTTPException(status_code=500, detail="Ошибка получения данных")
        data = r.json()
    else:
        data = []
    if not data:
        return { "error": "Нет данных для экспорта" }
    df = pd.DataFrame(data)
    df.rename(columns={
        "id":"ID","date_time":"Дата и время","location":"Участок","rig_number":"№ агрегата",
        "meterage":"Метраж","pogon":"Погонометр","operation":"Вид операции",
        "note":"Примечание","operator_name":"Ответственное лицо","created_at":"created_at"
    }, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition":"attachment; filename=svodka.xlsx"})

@app.post('/users/create')
def create_user(username: str = Form(...), password: str = Form(...), role: str = Form(...),
                full_name: str = Form(""), location: str = Form(""), unit: str = Form("")):
    pwd_hash = hash_password(password)
    user_obj = {
        "username": username,
        "password_hash": pwd_hash,
        "role": role,
        "full_name": full_name,
        "location": location,
        "unit": unit,
        "created_at": datetime.now().astimezone().isoformat()
    }
    if SUPABASE_API_KEY:
        r = supabase_post('/rest/v1/users', user_obj)
        if not r or r.status_code not in (200,201):
            raise HTTPException(status_code=500, detail=r.text if r else "Supabase error")
        return { "message": "Пользователь создан" }
    else:
        FALLBACK_USERS[username] = { "password_hash": pwd_hash, "role": role, "full_name": full_name, "location": location, "unit": unit }
        return { "message": "Пользователь создан (локально)" }
