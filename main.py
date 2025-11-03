from fastapi import FastAPI, Request, Form, Response, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, requests, pandas as pd
from itsdangerous import URLSafeSerializer
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ovkfakpwgvrpbnjbrkza.supabase.co")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "secret")
SESSION_KEY = os.environ.get("SESSION_KEY", "123456789abcdef")

s = URLSafeSerializer(SESSION_KEY, salt="session")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def supabase_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def supabase_insert(table, payload):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.post(url, json=payload, headers=HEADERS)
    r.raise_for_status()
    return r.json()

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login_worker")

@app.get("/login_worker")
def login_worker_get(request: Request):
    return templates.TemplateResponse("login_worker.html", {"request": request})

@app.post("/login_worker")
def login_worker_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        users = supabase_get("users", f"?username=eq.{username}&select=*")
        if not users:
            return templates.TemplateResponse("login_worker.html", {"request": request, "error": "Неверный логин/пароль"})
        user = users[0]
        if user.get("password") != password:
            return templates.TemplateResponse("login_worker.html", {"request": request, "error": "Неверный логин/пароль"})
        token = s.dumps({"id": user.get("id"), "username": user.get("username"), "role": user.get("role"), "full_name": user.get("full_name"), "location": user.get("location"), "rig_number": user.get("rig_number", "")})
        response = RedirectResponse(url="/form", status_code=303)
        response.set_cookie("session", token, httponly=True)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/login_dispatcher")
def login_dispatcher_get(request: Request):
    return templates.TemplateResponse("login_dispatcher.html", {"request": request})

@app.post("/login_dispatcher")
def login_dispatcher_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        users = supabase_get("users", f"?username=eq.{username}&select=*")
        if not users:
            return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин/пароль"})
        user = users[0]
        if user.get("password") != password or user.get("role") != "dispatcher":
            return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин/пароль"})
        token = s.dumps({"id": user.get("id"), "username": user.get("username"), "role": user.get("role"), "full_name": user.get("full_name")})
        response = RedirectResponse(url="/dispatcher", status_code=303)
        response.set_cookie("session", token, httponly=True)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        return s.loads(token)
    except Exception:
        return None

@app.get("/form")
def form_get(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("form.html", {"request": request, "user": user, "now": datetime.utcnow().isoformat()})

@app.post("/submit")
def submit(request: Request, location: str = Form(...), rig_number: str = Form(...), meterage: float = Form(...), pogon: str = Form(...), operation_type: str = Form(...), note: str = Form(""), operator_name: str = Form("")):
    user = get_current_user(request)
    created_at = datetime.utcnow().isoformat()
    payload = {
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "operation_type": operation_type,
        "note": note,
        "operator_name": operator_name or (user.get("full_name") if user else ""),
        "created_at": created_at
    }
    try:
        supabase_insert("reports", payload)
        return RedirectResponse("/form", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dispatcher")
def dispatcher_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login_dispatcher")
    try:
        reports = supabase_get("reports", "?select=*")
    except Exception as e:
        reports = []
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports})

@app.get("/export_excel")
def export_excel(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login_dispatcher")
    try:
        data = supabase_get("reports", "?select=*")
        df = pd.DataFrame(data)
        out = "/tmp/reports_export.xlsx"
        df.to_excel(out, index=False)
        return FileResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="reports.xlsx")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logout")
def logout():
    response = RedirectResponse("/login_worker")
    response.delete_cookie("session")
    return response
