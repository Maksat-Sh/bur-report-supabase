from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
import os

app = FastAPI()

# Настройки Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

# Папки
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/submit")
async def submit_report(
    date: str = Form(...),
    section: str = Form(...),
    rig_number: str = Form(...),
    meterage: float = Form(...),
    pogon: float = Form(...),
    notes: str = Form(...)
):
    data = {
        "date": date,
        "section": section,
        "rig_number": rig_number,
        "meterage": meterage,
        "pogon": pogon,
        "notes": notes
    }
    response = supabase.table("reports").insert(data).execute()
    return {"message": "Report submitted successfully"}


@app.get("/api/reports")
async def get_reports():
    response = supabase.table("reports").select("*").execute()
    return response.data


@app.get("/login")
async def login():
    return JSONResponse({"message": "Login page placeholder"})
