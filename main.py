
import os
import io
import requests
import pandas as pd
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime
import bcrypt

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY", "change_this_secret")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("DEBUG SUPABASE_URL =", SUPABASE_URL)
    print("DEBUG SUPABASE_API_KEY =", SUPABASE_API_KEY)
    raise RuntimeError("SUPABASE_URL или SUPABASE_API_KEY не найдены в .env")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_KEY)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def supabase_get(table, params=''):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    r = requests.get(url, headers=SUPABASE_HEADERS)
    r.raise_for_status()
    return r.json()

def supabase_insert(table, payload):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.post(url, headers=SUPABASE_HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def get_user_by_username(username):
    users = supabase_get("users", f"?username=eq.{username}&select=*")
    return users[0] if users else None

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    role = user.get("role")
    if role in ("dispatcher", "admin"):
        return RedirectResponse("/dispatcher")
    return RedirectResponse("/form")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    pw_hash = user.get("password_hash")
    if not pw_hash or not bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    session_user = {
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name") or "",
        "location": user.get("location"),
        "rig_number": user.get("rig_number")
    }
    request.session["user"] = session_user
    return RedirectResponse("/", status_code=303)

@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("driller",):
        return RedirectResponse("/login")
    sites = ["Карамурын", "Ирколь", "Хорасан", "Заречное", "Степногорск"]
    return templates.TemplateResponse("form.html", {"request": request, "user": user, "sites": sites})

@app.post("/submit")
def submit_report(request: Request,
                  meterage: float = Form(...),
                  pogon: float = Form(...),
                  operation_type: str = Form(""),
                  note: str = Form("") ):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    report = {
        "date_time": datetime.now().astimezone().isoformat(),
        "location": user.get("location"),
        "rig_number": user.get("rig_number"),
        "meterage": meterage,
        "pogon": pogon,
        "operation_type": operation_type,
        "operator_name": user.get("full_name"),
        "note": note
    }
    try:
        supabase_insert("reports", report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse({"message": "ok"})

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher", "admin"):
        return RedirectResponse("/login")
    try:
        reports = supabase_get("reports", "?select=*&order=date_time.desc")
    except Exception:
        reports = []
    try:
        users = supabase_get("users", "?select=id,username,role,full_name,location,rig_number,created_at")
    except Exception:
        users = []
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "users": users})

@app.post("/api/users/create")
def api_create_user(username: str = Form(...), password: str = Form(...), role: str = Form(...), full_name: str = Form(...), location: str = Form(None), rig_number: str = Form(None)):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    payload = {
        "username": username,
        "password_hash": pw_hash,
        "role": role,
        "full_name": full_name,
        "location": location,
        "rig_number": rig_number
    }
    try:
        supabase_insert("users", payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}

@app.post("/api/users/delete")
def api_delete_user(id: int = Form(...)):
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{id}"
    r = requests.delete(url, headers=SUPABASE_HEADERS)
    r.raise_for_status()
    return {"status": "ok"}

@app.get("/export_excel")
def export_excel():
    try:
        data = supabase_get("reports", "?select=*&order=date_time.desc")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not data:
        df = pd.DataFrame([{"ID": "", "Дата и время": "", "Участок": "", "№ агрегата": "", "Метраж": "", "Погонометр": "", "Виды операции": "", "Ответственное лицо": "", "Примечание": ""}])
    else:
        df = pd.DataFrame(data)
        df.rename(columns={
            "id": "ID",
            "date_time": "Дата и время",
            "location": "Участок",
            "rig_number": "№ агрегата",
            "meterage": "Метраж",
            "pogon": "Погонометр",
            "operation_type": "Виды операции",
            "note": "Примечание",
            "operator_name": "Ответственное лицо"
        }, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=svodka.xlsx"})

@app.get("/health")
def health():
    return {"status": "ok"}
