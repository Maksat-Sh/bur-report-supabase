from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from datetime import datetime
import httpx
import os

app = FastAPI()

# ---------- SETTINGS ----------
SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- REPORT MODEL ----------
class Report(BaseModel):
    bur: str
    section: str
    bur_no: str
    pogonometr: float
    footage: float
    operation_type: str
    operation: str
    note: str
    created_at: datetime


# ---------- AUTH ----------
def require_login(request: Request):
    return "user" in request.session


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # диспетчер
    if username == "admin" and password == "1234":
        request.session["user"] = "admin"
        return RedirectResponse("/dispatcher", status_code=302)

    # буровик
    if password == "0000":
        request.session["user"] = username
        return RedirectResponse("/burform", status_code=302)

    return RedirectResponse("/login?error=1", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------- БУРОВАЯ ФОРМА ----------
@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    if not require_login(request):
        return RedirectResponse("/login")
    return templates.TemplateResponse("burform.html", {"request": request})


# ---------- ПРИЕМ СВОДКИ ----------
@app.post("/submit_report")
async def submit_report(
    request: Request,
    bur: str = Form(...),
    section: str = Form(...),
    bur_no: str = Form(...),
    pogonometr: float = Form(...),
    footage: float = Form(...),
    operation_type: str = Form(...),
    operation: str = Form(...),
    note: str = Form(...),
):

    data = {
        "bur": bur,
        "section": section,
        "bur_no": bur_no,
        "pogonometr": pogonometr,
        "footage": footage,
        "operation_type": operation_type,
        "operation": operation,
        "note": note,
        "created_at": datetime.utcnow().isoformat()
    }

    print("=== REPORT DATA BEFORE SENDING TO SUPABASE ===")
    print(data)
    print("================================================")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/reports",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json=data
            )

            if resp.status_code >= 300:
                print("SUPABASE ERROR:", resp.status_code, resp.text)
                return RedirectResponse("/burform?fail=1", status_code=302)

        except Exception as e:
            print("ERROR SENDING REPORT:", e)
            return RedirectResponse("/burform?fail=1", status_code=302)

    return RedirectResponse("/burform?ok=1", status_code=302)


# ---------- ДИСПЕТЧЕР ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not require_login(request):
        return RedirectResponse("/login")

    return templates.TemplateResponse("dispatcher.html", {"request": request})


# ---------- STARTUP ----------
@app.on_event("startup")
async def startup_event():
    print("Supabase REST ready:", SUPABASE_URL)
