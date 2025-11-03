
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templates import Jinja2Templates
from supabase import create_client, Client
import os, hashlib

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login_worker")

@app.get("/login_worker", response_class=HTMLResponse)
async def login_worker_get(request: Request):
    return templates.TemplateResponse("login_worker.html", {"request": request})

@app.post("/login_worker", response_class=HTMLResponse)
async def login_worker_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed = hash_password(password)
    res = supabase.table("users").select("*").eq("username", username).execute()
    if res.data and res.data[0]["password_hash"] == hashed and res.data[0]["role"] == "worker":
        return RedirectResponse("/form", status_code=303)
    return templates.TemplateResponse("login_worker.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher_get(request: Request):
    return templates.TemplateResponse("login_dispatcher.html", {"request": request})

@app.post("/login_dispatcher", response_class=HTMLResponse)
async def login_dispatcher_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed = hash_password(password)
    res = supabase.table("users").select("*").eq("username", username).execute()
    if res.data and res.data[0]["password_hash"] == hashed and res.data[0]["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=303)
    return templates.TemplateResponse("login_dispatcher.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit_report")
async def submit_report(
    location: str = Form(...),
    rig_number: str = Form(...),
    meterage: str = Form(...),
    pogon: str = Form(...),
    note: str = Form(...),
    operator_name: str = Form(...),
):
    supabase.table("reports").insert({
        "location": location,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "note": note,
        "operator_name": operator_name,
    }).execute()
    return RedirectResponse("/form", status_code=303)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    reports = supabase.table("reports").select("*").order("id", desc=True).execute()
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports.data or []})
