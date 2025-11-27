from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import requests
from datetime import datetime
import os

app = FastAPI()

# --- SESSION ---
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

# --- STATIC ---
app.mount("/static", StaticFiles(directory="static"), name="static")

SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_user(request: Request):
    return request.session.get("user")


# ==========================
# LOGIN / LOGOUT
# ==========================
@app.get("/login")
async def login_page():
    return HTMLResponse(open("templates/login.html", encoding="utf-8").read())

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "dispatcher" and password == "1234":
        request.session["user"] = "dispatcher"
        return RedirectResponse("/dispatcher", status_code=302)

    if username == "bur" and password == "1111":
        request.session["user"] = "bur"
        return RedirectResponse("/burform", status_code=302)

    return RedirectResponse("/login?error=1", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ==========================
# BUR FORM
# ==========================
@app.get("/burform")
async def burform_page(request: Request, user=Depends(get_user)):
    if user != "bur":
        return RedirectResponse("/login")
    return HTMLResponse(open("templates/burform.html", encoding="utf-8").read())


@app.post("/submit_report")
async def submit_report(
    request: Request,
    bur: str = Form(...),
    section: str = Form(...),
    location: str = Form(...),
    bur_no: str = Form(...),
    pogonometr: float = Form(...),
    footage: float = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form(...)
):
    # === Приводим числовые поля к int (как в вашей БД) ===
    pogonometr = int(pogonometr)
    footage = int(footage)

    # === Готовим структуру точь-в-точь как в Supabase ===
    data = {
        "bur": bur,
        "section": section,
        "location": location,
        "bur_no": bur_no,
        "pogonometr": pogonometr,
        "footage": footage,
        "operation_type": operation_type,
        "operation": operation,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    # === Отправка в Supabase ===
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    print("\n=== REPORT DATA BEFORE SENDING TO SUPABASE ===")
    print(data)
    print("================================================")

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/reports",
        json=data,
        headers=headers
    )

    if response.status_code >= 300:
        print("Failed to POST report:", response.text)

    return RedirectResponse("/burform?success=1", status_code=302)


# ==========================
# DISPATCHER PAGE
# ==========================
@app.get("/dispatcher")
async def dispatcher_page(request: Request, user=Depends(get_user)):
    if user != "dispatcher":
        return RedirectResponse("/login")
    return HTMLResponse(open("templates/dispatcher.html", encoding="utf-8").read())


# ==========================
# API — GET REPORTS
# ==========================
@app.get("/api/reports")
async def api_reports(request: Request, user=Depends(get_user)):
    if user != "dispatcher":
        return {"error": "Unauthorized"}

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/reports?select=*",
        headers=headers
    )

    return response.json()
