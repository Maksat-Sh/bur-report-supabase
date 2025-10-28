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

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("DEBUG SUPABASE_URL =", os.getenv("SUPABASE_URL"))
    print("DEBUG SUPABASE_API_KEY =", os.getenv("SUPABASE_API_KEY"))
    raise RuntimeError("SUPABASE_URL или SUPABASE_API_KEY не найдены в .env")

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_KEY","supersecret"))

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

LOCAL_USERS = {
    "dispatcher": {"username":"dispatcher","password":"dispatch123","role":"dispatcher","full_name":"Диспетчер"},
    "bur1": {"username":"bur1","password":"123","role":"driller","full_name":"МБУ 1"},
}

def supabase_get(path, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{path}{params}"
    return requests.get(url, headers=HEADERS)

def supabase_post(path, json_data):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    return requests.post(url, headers=HEADERS, json=json_data)

def supabase_delete(path):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    return requests.delete(url, headers=HEADERS)

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    if user.get("role") in ("dispatcher","admin"):
        return RedirectResponse("/dispatcher")
    return RedirectResponse("/form")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        res = supabase_get("users", "?select=*")
        if res.status_code == 200:
            users = res.json()
            for u in users:
                if u.get("username") == username and u.get("password") == password:
                    request.session["user"] = {"username": username, "role": u.get("role"), "full_name": u.get("full_name")}
                    return RedirectResponse("/", status_code=303)
    except Exception:
        pass
    lu = LOCAL_USERS.get(username)
    if lu and lu["password"] == password:
        request.session["user"] = {"username": username, "role": lu["role"], "full_name": lu["full_name"]}
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "driller":
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user, "message": ""})

@app.post("/submit")
def submit_report(
    request: Request,
    date_time: str = Form(...),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(""),
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    full_name = user.get("full_name", user.get("username"))
    report = {
        "date_time": date_time,
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "operator_name": full_name
    }
    try:
        res = supabase_post("reports", report)
        if res.status_code in (201, 200):
            return templates.TemplateResponse("form.html", {"request": request, "user": user, "message": "Успешно отправлено"})
        else:
            return templates.TemplateResponse("form.html", {"request": request, "user": user, "message": f"Ошибка: {res.text}"})
    except Exception as e:
        return templates.TemplateResponse("form.html", {"request": request, "user": user, "message": f"Ошибка: {e}"})

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher","admin"):
        return RedirectResponse("/login")
    try:
        r = supabase_get("reports", "?select=*,created_at")
        reports = r.json() if r.status_code==200 else []
    except Exception:
        reports = []
    try:
        u = supabase_get("users", "?select=*")
        users = u.json() if u.status_code==200 else []
    except Exception:
        users = []
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "users": users})

@app.post("/users/add")
def add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...), full_name: str = Form("")):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher","admin"):
        raise HTTPException(status_code=401)
    new_user = {"username": username, "password": password, "role": role, "full_name": full_name}
    try:
        res = supabase_post("users", new_user)
        if res.status_code in (201,200):
            return RedirectResponse("/dispatcher", status_code=303)
        else:
            raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/delete")
def delete_user(request: Request, username: str = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") not in ("dispatcher","admin"):
        raise HTTPException(status_code=401)
    try:
        res = supabase_delete(f"users?username=eq.{username}")
        if res.status_code in (204,200):
            return RedirectResponse("/dispatcher", status_code=303)
        else:
            raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export_excel")
def export_excel():
    try:
        r = supabase_get("reports", "?select=*")
        data = r.json() if r.status_code==200 else []
    except Exception:
        data = []
    if not data:
        return {"error": "Нет данных для экспорта"}
    df = pd.DataFrame(data)
    rename_map = {
        "id":"ID","date_time":"Дата и время","location":"Участок","rig_number":"Номер буровой",
        "meterage":"Метраж","pogon":"Погонометр","note":"Примечание","operator_name":"Ответственное лицо","created_at":"created_at"
    }
    df.rename(columns=rename_map, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сводка")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=svodka.xlsx"})