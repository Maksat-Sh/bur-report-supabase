import os
import io
import json
import requests
import pandas as pd
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime
import bcrypt

# Load .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
# prefer service role key if present, otherwise anon key
SUPABASE_API_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY") or "dev-secret-session-key"

print("DEBUG SUPABASE_URL =", SUPABASE_URL)
print("DEBUG SUPABASE_API_KEY =", "SET" if SUPABASE_API_KEY else "NOT SET")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("Warning: SUPABASE_URL or SUPABASE_API_KEY not set. The app will run in degraded mode using a local fallback USERS dict. To use Supabase ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY) are set in your environment.")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY or "",
    "Authorization": f"Bearer {SUPABASE_API_KEY}" if SUPABASE_API_KEY else "",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_KEY)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Local fallback users (used if Supabase not configured)
LOCAL_USERS = {
    "dispatcher": {"username": "dispatcher", "password_hash": bcrypt.hashpw(b"12345", bcrypt.gensalt()).decode(), "role": "dispatcher", "full_name": "Диспетчер"},
    "bur1": {"username": "bur1", "password_hash": bcrypt.hashpw(b"123", bcrypt.gensalt()).decode(), "role": "driller", "full_name": "Бурильщик 1"},
}

def supabase_get(table, params=""):
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        return None, {"error": "supabase not configured"}
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    r = requests.get(url, headers=SUPABASE_HEADERS)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def supabase_post(table, payload):
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        return None, {"error": "supabase not configured"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.post(url, headers=SUPABASE_HEADERS, json=payload)
    try:
        return r.status_code, r.json() if r.text else {}
    except Exception:
        return r.status_code, r.text

def supabase_delete(table, params=""):
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        return None, {"error": "supabase not configured"}
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    r = requests.delete(url, headers=SUPABASE_HEADERS)
    try:
        return r.status_code, r.json() if r.text else {}
    except Exception:
        return r.status_code, r.text

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user"):
        role = request.session["user"]["role"]
        if role in ("dispatcher","admin"):
            return RedirectResponse("/dispatcher")
        elif role == "driller":
            return RedirectResponse("/form")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Try Supabase first
    if SUPABASE_URL and SUPABASE_API_KEY:
        status, users = supabase_get("users", params=f"?username=eq.{username}&select=*")
        if status == 200 and users:
            user = users[0]
            pwd_hash = user.get("password_hash") or user.get("password") or ""
            if isinstance(pwd_hash, str):
                try:
                    if bcrypt.checkpw(password.encode(), pwd_hash.encode()):
                        # store minimal session info
                        request.session["user"] = {"username": user.get("username"), "role": user.get("role"), "full_name": user.get("full_name") or user.get("username")}
                        return RedirectResponse("/", status_code=303)
                except Exception:
                    pass
        # fallthrough to local
    # Local fallback
    u = LOCAL_USERS.get(username)
    if u and bcrypt.checkpw(password.encode(), u["password_hash"].encode()):
        request.session["user"] = {"username": u["username"], "role": u["role"], "full_name": u.get("full_name", u["username"])}
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- Driller form ---
@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "driller":
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})

@app.post("/submit")
def submit_report(
    request: Request,
    date_time: str = Form(None),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    operator_name: str = Form(None),
    operation_type: str = Form(None),
    note: str = Form(""),
):
    user = request.session.get("user")
    if user and not operator_name:
        operator_name = user.get("full_name", user.get("username"))

    payload = {
        "date_time": date_time or (datetime.utcnow().isoformat()),
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "operator_name": operator_name,
        "operation_type": operation_type,
        "note": note,
    }
    status, resp = supabase_post("reports", payload)
    if status and status in (200,201,204):
        return {"message": "ok"}
    # if supabase not configured, return ok but store nowhere
    if resp and isinstance(resp, dict) and resp.get("error"):
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении: {resp.get('error')}")
    # fallback
    return {"message":"ok (local)"}

# --- Dispatcher page ---
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user["role"] not in ("dispatcher","admin"):
        return RedirectResponse("/login")

    status, reports = supabase_get("reports", params="?select=*,created_at") if SUPABASE_URL and SUPABASE_API_KEY else (None, [])
    if status and status != 200:
        reports = []
    reports = reports or []

    u_status, users = supabase_get("users", params="?select=id,username,role,created_at") if SUPABASE_URL and SUPABASE_API_KEY else (None, [])
    users = users or []

    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "users": users})

# --- Users API (create / list / delete) ---
@app.get("/api/users")
def api_list_users():
    status, users = supabase_get("users", params="?select=id,username,role,created_at") if SUPABASE_URL and SUPABASE_API_KEY else (None, list(LOCAL_USERS.values()))
    return users or []

@app.post("/api/users")
def api_create_user(username: str = Form(...), password: str = Form(...), role: str = Form("driller")):
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    payload = {"username": username, "password_hash": pwd_hash, "role": role}
    status, resp = supabase_post("users", payload)
    if status and status in (200,201,204):
        return {"status":"ok"}
    if resp and isinstance(resp, dict) and resp.get("error"):
        raise HTTPException(status_code=500, detail=resp.get("error"))
    LOCAL_USERS[username] = {"username": username, "password_hash": pwd_hash, "role": role}
    return {"status":"ok (local)"}

@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int):
    status, resp = supabase_delete("users", params=f"?id=eq.{user_id}")
    if status and status in (200,204):
        return {"status":"deleted"}
    return {"status":"failed", "detail": resp}

# --- Export to Excel ---
@app.get("/export_excel")
def export_excel():
    status, data = supabase_get("reports", params="?select=id,date_time,location,rig_number,meterage,pogon,operator_name,note,created_at") if SUPABASE_URL and SUPABASE_API_KEY else (None, [])
    data = data or []
    if not data:
        return {"error":"Нет данных для экспорта"}
    df = pd.DataFrame(data)
    df.rename(columns={
        "id":"ID",
        "date_time":"Дата и время",
        "location":"МБУ",
        "rig_number":"Номер буровой",
        "meterage":"Метраж",
        "pogon":"Погонометр",
        "operator_name":"Ответственное лицо",
        "note":"Примечание",
        "created_at":"created_at",
    }, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition":"attachment; filename=svodka.xlsx"})