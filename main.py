import os
import requests
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- static + templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- простейшая авторизация ---
users = {
    "bur1": {"password": "123", "full_name": "Бурильщик 1", "role": "driller"},
    "bur2": {"password": "123", "full_name": "Бурильщик 2", "role": "driller"},
    "dispatcher": {"password": "dispatch123", "full_name": "Диспетчер", "role": "dispatcher"},
}


@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = users.get(username)
    if not user or user["password"] != password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    response = RedirectResponse("/dispatcher" if user["role"] == "dispatcher" else "/form", status_code=302)
    response.set_cookie("username", username)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("username")
    return response


def get_current_user(request: Request):
    username = request.cookies.get("username")
    return users.get(username) if username in users else None


# --- форма буровика ---
@app.get("/form", response_class=HTMLResponse)
def form_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("form.html", {"request": request, "user": user})


@app.post("/submit")
def submit_report(
    request: Request,
    date_time: str = Form(...),
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    note: str = Form(...),
):
    username = request.cookies.get("username")
    user = users.get(username)
    if not user:
        return {"error": "Unauthorized"}

    data = {
        "date_time": date_time,
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "operator_name": user["full_name"]
    }

    res = requests.post(f"{SUPABASE_URL}/rest/v1/reports", headers=HEADERS, json=data)
    if res.status_code == 201:
        return {"message": "Report submitted successfully"}
    else:
        return {"error": res.text}


# --- страница диспетчера ---
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login")
    return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user})


@app.get("/api/reports")
def get_reports():
    res = requests.get(f"{SUPABASE_URL}/rest/v1/reports?select=*", headers=HEADERS)
    return res.json()


@app.get("/export")
def export_excel():
    import pandas as pd
    from io import BytesIO
    res = requests.get(f"{SUPABASE_URL}/rest/v1/reports?select=*", headers=HEADERS)
    df = pd.DataFrame(res.json())
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    from fastapi.responses import StreamingResponse
from fastapi.responses import StreamingResponse
import io
import pandas as pd

@app.get("/export")
async def export_to_excel():
    reports = await get_reports()
    if not reports:
        return {"error": "Нет данных для экспорта"}

    df = pd.DataFrame(reports)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=reports.xlsx"
        }
    )


