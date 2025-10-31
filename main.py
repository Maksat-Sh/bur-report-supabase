from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import requests
import bcrypt
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_REST_URL = f"{SUPABASE_URL}/rest/v1"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# ---------- Главная ----------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/dispatcher")

# ---------- Страница диспетчера ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})

# ---------- Страница пользователей ----------
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

# ---------- Получить всех пользователей ----------
@app.get("/api/users")
async def get_users():
    r = requests.get(f"{SUPABASE_REST_URL}/users", headers=headers)
    return JSONResponse(r.json())

# ---------- Создать нового пользователя ----------
@app.post("/users/create")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(None),
    role: str = Form("driller"),
    fio: str = Form(None),
    location: str = Form(None),
):
    try:
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        data = {
            "username": username,
            "password": password,  # сохраняем отдельно, как ты хотел
            "password_hash": password_hash,
            "full_name": full_name,
            "fio": fio,
            "location": location,
            "role": role,
            "created_at": datetime.now().isoformat()
        }
        r = requests.post(f"{SUPABASE_REST_URL}/users", headers=headers, json=data)
        if r.status_code >= 400:
            return JSONResponse({"error": r.text}, status_code=500)
        return JSONResponse({"message": "Пользователь успешно создан"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------- Форма буровика ----------
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def submit_report(
    date_time: str = Form(...),
    location: str = Form(...),
    drill_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(None),
):
    try:
        data = {
            "date_time": date_time,
            "location": location,
            "drill_number": drill_number,
            "meterage": meterage,
            "pogon": pogon,
            "note": note,
            "created_at": datetime.now().isoformat()
        }
        r = requests.post(f"{SUPABASE_REST_URL}/reports", headers=headers, json=data)
        if r.status_code >= 400:
            return JSONResponse({"error": r.text}, status_code=500)
        return JSONResponse({"message": "Сводка успешно отправлена"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
