import os
import io
import requests
import pandas as pd
import bcrypt
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY", "replace_with_a_secure_random_value")

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

LOCAL_USERS = {
    "bur1": {"password": "123", "role": "driller", "full_name": "Бурильщик 1"},
    "dispatcher": {"password": "dispatch123", "role": "dispatcher", "full_name": "Диспетчер"},
    "admin": {"password": "9999", "role": "admin", "full_name": "Админ"},
}

def supabase_get(path: str):
    url = SUPABASE_URL.rstrip('/') + path
    r = requests.get(url, headers=SUPABASE_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()

@app.get('/', response_class=HTMLResponse)
def root(request: Request):
    user = request.session.get("user")
    if user:
        if user["role"] in ("dispatcher", "admin"):
            return RedirectResponse("/dispatcher")
        return RedirectResponse("/form")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        users = supabase_get("/rest/v1/users?select=username,password_hash,role,full_name&username=eq." + username)
        if users and isinstance(users, list) and len(users) > 0:
            u = users[0]
            pw_hash = u.get("password_hash") or ""
            if pw_hash and bcrypt.checkpw(password.encode(), pw_hash.encode()):
                request.session["user"] = {"username": username, "role": u.get("role", "driller"), "full_name": u.get("full_name", username)}
                return RedirectResponse("/", status_code=303)
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    except Exception:
        u = LOCAL_USERS.get(username)
        if u and u["password"] == password:
            request.session["user"] = {"username": username, "role": u["role"], "full_name": u.get("full_name", username)}
            return RedirectResponse("/", status_code=303)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("driller", "admin"):
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})

@app.post("/submit")
def submit_report(request: Request,
                  date_time: str = Form(...),
                  location: str = Form(...),
                  rig_number: str = Form(...),
                  meterage: float = Form(...),
                  pogon: float = Form(...),
                  note: str = Form("")):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    operator = user.get("full_name") or user.get("username")
    payload = {
        "date_time": date_time,
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note or "",
        "operator_name": operator
    }
    res = requests.post(f"{SUPABASE_URL.rstrip('/')}/rest/v1/reports", headers=SUPABASE_HEADERS, json=payload, timeout=10)
    if res.status_code not in (200,201):
        return JSONResponse(status_code=500, content={"error": res.text})
    return {"message": "Сводка успешно отправлена"}

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher","admin"):
        return RedirectResponse("/login")
    try:
        reports = supabase_get("/rest/v1/reports?select=*")
        if isinstance(reports, dict):
            reports = [reports]
    except Exception:
        reports = []
    try:
        users = supabase_get("/rest/v1/users?select=id,username,role,created_at")
    except Exception:
        users = []
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "users": users})

@app.get("/export_excel")
def export_excel():
    try:
        r = requests.get(f"{SUPABASE_URL.rstrip('/')}/rest/v1/reports?select=*", headers=SUPABASE_HEADERS, timeout=10)
        data = r.json()
        if data is None or data == []:
            return JSONResponse(status_code=404, content={"error": "Нет данных для экспорта"})
        if isinstance(data, dict):
            data = [data]
        df = pd.DataFrame(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if df.empty:
        return JSONResponse(status_code=404, content={"error": "Нет данных для экспорта"})
    df.rename(columns={"id":"ID","date_time":"Дата и время","location":"МБУ","rig_number":"Номер буровой","meterage":"Метраж","pogon":"Погонометр","note":"Примечание","operator_name":"Ответственное лицо"}, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=svodka.xlsx"})

@app.get('/users', response_class=HTMLResponse)
def users_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher","admin"):
        return RedirectResponse('/login')
    try:
        users = supabase_get('/rest/v1/users?select=id,username,role,created_at')
    except Exception:
        users = []
    return templates.TemplateResponse('users.html', {"request": request, "user": user, "users": users})

@app.post('/users/create')
def create_user(username: str = Form(...), password: str = Form(...), role: str = Form('driller')):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    payload = {'username': username, 'password_hash': pw_hash, 'role': role}
    res = requests.post(f"{SUPABASE_URL.rstrip('/')}/rest/v1/users", headers=SUPABASE_HEADERS, json=payload, timeout=10)
    if res.status_code not in (200,201):
        return JSONResponse(status_code=500, content={'error': res.text})
    return RedirectResponse('/users', status_code=303)

@app.post('/users/delete')
def delete_user(id: int = Form(...)):
    res = requests.delete(f"{SUPABASE_URL.rstrip('/')}/rest/v1/users?id=eq.{id}", headers=SUPABASE_HEADERS, timeout=10)
    if res.status_code not in (200,204):
        return JSONResponse(status_code=500, content={'error': res.text})
    return RedirectResponse('/users', status_code=303)
