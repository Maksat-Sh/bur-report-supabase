from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import pandas as pd
from datetime import datetime
from itsdangerous import URLSafeSerializer
import bcrypt

app = FastAPI()

# --- CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY", "123456789abcdef")
serializer = URLSafeSerializer(SESSION_KEY, salt="session")

# --- PATHS ---
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- LOGIN PAGE ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_action(username: str = Form(...), password: str = Form(...)):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    if not res.ok or not res.json():
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    user = res.json()[0]
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = serializer.dumps({"username": username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session", token)
    return response

# --- AUTH DEPENDENCY ---
def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        data = serializer.loads(token)
        return data["username"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- DISPATCHER PAGE ---
@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request, user: str = Depends(get_current_user)):
    # Получаем сводки
    reports = requests.get(
        f"{SUPABASE_URL}/rest/v1/reports?select=*",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    ).json()

    # Получаем пользователей
    users = requests.get(
        f"{SUPABASE_URL}/rest/v1/users?select=*",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    ).json()

    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports, "users": users})

# --- ADD REPORT (MБУ форма) ---
@app.get("/mbu", response_class=HTMLResponse)
async def mbu_form(request: Request):
    return templates.TemplateResponse("mbu.html", {"request": request})

@app.post("/submit")
async def submit_report(
    date_time: str = Form(...),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(...),
    operator_name: str = Form(...),
    operation: str = Form(...)
):
    data = {
        "date_time": date_time,
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "operator_name": operator_name,
        "operation": operation,
        "created_at": datetime.utcnow().isoformat()
    }
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/reports",
        json=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
    )
    if res.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения: {res.text}")
    return {"message": "Успешно отправлено"}

# --- EXPORT EXCEL ---
@app.get("/export")
async def export_excel(user: str = Depends(get_current_user)):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/reports?select=*",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    reports = res.json()
    if not reports:
        return {"message": "Нет данных"}
    df = pd.DataFrame(reports)
    file_path = "/tmp/reports.xlsx"
    df.to_excel(file_path, index=False)
    return FileResponse(file_path, filename="reports.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- ADD USER ---
@app.post("/add_user")
async def add_user(username: str = Form(...), password: str = Form(...), role: str = Form(...), user: str = Depends(get_current_user)):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    data = {"username": username, "password_hash": hashed, "role": role, "created_at": datetime.utcnow().isoformat()}
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/users",
        json=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
    )
    if res.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=f"Ошибка добавления: {res.text}")
    return RedirectResponse("/", status_code=302)

# --- DELETE USER ---
@app.post("/delete_user")
async def delete_user(user_id: int = Form(...), user: str = Depends(get_current_user)):
    res = requests.delete(
        f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    if not res.ok:
        raise HTTPException(status_code=500, detail="Ошибка удаления")
    return RedirectResponse("/", status_code=302)
