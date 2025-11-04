"""
main.py - FastAPI app for bur-report using Supabase REST API (httpx).
Env variables required:
  SUPABASE_URL - e.g. https://xxxx.supabase.co
  SUPABASE_API_KEY - anon/public or service_role key
  SESSION_KEY - any string used as a salt (not cryptographic here)
Run:
  uvicorn main:app --host 0.0.0.0 --port 10000
"""

import os
import io
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from passlib.hash import bcrypt
import pandas as pd  # for export
from pydantic import BaseModel
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password_plain_or_hash(plain_password, hashed_password):
    try:
        if hashed_password.startswith("$2b$"):  # bcrypt
            return pwd_context.verify(plain_password, hashed_password)
        return plain_password == hashed_password
    except Exception:
        return False

# Config from env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY", "dev-session-key")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_API_KEY environment variables.")

REST_BASE = SUPABASE_URL.rstrip("/") + "/rest/v1"
SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- Utilities -------------------------------------------------------
async def supabase_get(path: str, params: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    url = f"{REST_BASE}/{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=SUPABASE_HEADERS, params=params)
        r.raise_for_status()
        return r.json()


async def supabase_post(table: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    r = httpx.post(url, headers=headers, json=data)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text}



async def supabase_patch(path: str, payload: Dict[str, Any], params: Dict[str, str] | None = None) -> Any:
    url = f"{REST_BASE}/{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(url, headers=SUPABASE_HEADERS, json=payload, params=params)
        r.raise_for_status()
        return r.json()


async def supabase_delete(path: str, params: Dict[str, str] | None = None) -> Any:
    url = f"{REST_BASE}/{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(url, headers=SUPABASE_HEADERS, params=params)
        r.raise_for_status()
        return r


# ---------- Auth helpers ---------------------------------------------------
async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    # Supabase REST: /users?username=eq.{username}&select=*
    res = await supabase_get("users", params={"username": f"eq.{username}", "select": "*"})
    if res:
        return res[0]
    return None


def verify_password_plain_or_hash(stored: Dict[str, Any], password: str) -> bool:
    """
    users table may have either:
      - password_hash (bcrypt)
      - password (plain)  <-- not recommended but allowed for backward compat
    This function checks either.
    """
    if not stored:
        return False
    ph = stored.get("password_hash") or stored.get("password")
    if not ph:
        return False
    try:
        # try bcrypt verify if looks like bcrypt
        if ph.startswith("$2"):
            return bcrypt.verify(password, ph)
    except Exception:
        pass
    # fallback plain equality
    return password == ph


def make_auth_response(redirect_to: str, username: str, role: str) -> RedirectResponse:
    resp = RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    # set simple cookie (expires in 1 day). For real production use signed tokens.
    resp.set_cookie("username", username, httponly=True, max_age=86400)
    resp.set_cookie("role", role, httponly=True, max_age=86400)
    return resp


def require_role(request: Request, allowed: List[str]) -> Optional[Dict[str, str]]:
    username = request.cookies.get("username")
    role = request.cookies.get("role")
    if not username or not role or role not in allowed:
        return None
    return {"username": username, "role": role}


# ---------- Routes ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/form")


# Worker form (burовик)
@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request):
    user = request.cookies.get("username")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})


class ReportIn(BaseModel):
    note: Optional[str]
    location: Optional[str]
    rig_number: Optional[str]
    meterage: Optional[float]
    pogon: Optional[str]
    operator_name: Optional[str]
    operation_type: Optional[str]


@app.post("/submit")
async def submit_report(request: Request,
                        location: str = Form(...),
                        rig_number: str = Form(...),
                        meterage: float = Form(...),
                        pogon: str = Form(""),
                        operator_name: str = Form(""),
                        operation_type: str = Form(""),
                        note: str = Form("")):
    payload = {
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "operator_name": operator_name,
        "operation_type": operation_type,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }
    # Insert into Supabase reports table
    await supabase_post("reports", payload)
    return RedirectResponse("/form", status_code=status.HTTP_303_SEE_OTHER)


# Worker login
@app.get("/login_worker", response_class=HTMLResponse)
async def login_worker_get(request: Request):
    return templates.TemplateResponse("login_worker.html", {"request": request, "error": None})


@app.post("/login_worker")
async def login_worker_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = await get_user_by_username(username)
    if not user or not verify_password_plain_or_hash(user, password):
        return templates.TemplateResponse("login_worker.html", {"request": request, "error": "Неверный логин или пароль"})
    # allowed roles for worker: 'worker', 'operator' (depends on your data)
    role = user.get("role", "worker")
    return make_auth_response("/form", username, role)


# Dispatcher login
@app.get("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher_get(request: Request):
    return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": None})


@app.post("/login_dispatcher")
async def login_dispatcher_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = await get_user_by_username(username)
    if not user:
        return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин или пароль"})
    
    password_hash = user.get("password_hash")
    if not verify_password_plain_or_hash(password, password_hash):
        return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин или пароль"})

    role = user.get("role", "dispatcher")
    return make_auth_response("/dispatcher", username, role)

# Dispatcher page (view and export)
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    auth = require_role(request, ["dispatcher", "admin"])
    if not auth:
        return RedirectResponse("/login_dispatcher")
    # Load all reports
    reports = await supabase_get("reports", params={"select": "*"})
    # Sort by created_at desc if exists
    try:
        reports_sorted = sorted(reports, key=lambda r: r.get("created_at") or "", reverse=True)
    except Exception:
        reports_sorted = reports
    return templates.TemplateResponse("dispatcher.html",
                                      {"request": request, "user": auth["username"], "reports": reports_sorted})


@app.get("/export_excel")
async def export_excel(request: Request):
    auth = require_role(request, ["dispatcher", "admin"])
    if not auth:
        return RedirectResponse("/login_dispatcher")
    reports = await supabase_get("reports", params={"select": "*"})
    # Build DataFrame and Excel bytes
    df = pd.DataFrame(reports)
    # rename columns to Russian names if desired
    mapping = {
        "id": "ID",
        "created_at": "Дата/Время",
        "location": "Участок",
        "rig_number": "Номер буровой",
        "meterage": "Метраж",
        "pogon": "Погонометр",
        "operator_name": "Буровик",
        "operation_type": "Тип операции",
        "note": "Примечание",
    }
    df = df.rename(columns=mapping)
    # Ensure order
    cols = [c for c in ["ID", "Дата/Время", "Участок", "Номер буровой", "Метраж", "Погонометр", "Буровик", "Тип операции", "Примечание"] if c in df.columns]
    df = df[cols] if cols else df
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="reports")
    buf.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/logout")
async def logout(request: Request):
    resp = RedirectResponse("/login_worker")
    resp.delete_cookie("username")
    resp.delete_cookie("role")
    return resp
