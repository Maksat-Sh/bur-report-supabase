from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, text
import os

# ================== НАСТРОЙКИ ==================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8iur433s73btijog-a/report_oag9"
)

engine = create_engine(DATABASE_URL)
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="super-secret-key"
)

templates = Jinja2Templates(directory="templates")

# ================== ВСПОМОГАТЕЛЬНОЕ ==================

def get_user(request: Request):
    return request.session.get("user")

def auth_required(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

# ================== ГЛАВНАЯ ==================

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

# ================== LOGIN ==================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    # ПРОСТОЙ ЛОГИН (как у тебя было)
    if password == "1234":
        request.session["user"] = username
        if username == "dispatcher":
            return RedirectResponse("/dispatcher", status_code=302)
        return RedirectResponse("/bur", status_code=302)

    return RedirectResponse("/login", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ================== БУРОВИК ==================

@app.get("/bur", response_class=HTMLResponse)
def bur_page(request: Request):
    if not get_user(request):
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "bur.html",
        {"request": request, "user": request.session["user"]}
    )

@app.post("/bur")
def submit_report(
    request: Request,
    area: str = Form(...),
    rig_number: str = Form(...),
    meters: float = Form(...),
    pogonometr: float = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(None)
):
    if not get_user(request):
        return RedirectResponse("/login", status_code=302)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO reports
                (bur, section, bur_no, footage, pogonometr, operation_type, person, note)
                VALUES
                (:bur, :section, :bur_no, :footage, :pogonometr, :operation, :person, :note)
            """),
            {
                "bur": request.session["user"],
                "section": area,
                "bur_no": rig_number,
                "footage": meters,
                "pogonometr": pogonometr,
                "operation": operation,
                "person": responsible,
                "note": note
            }
        )

    return RedirectResponse("/bur", status_code=302)

# ================== ДИСПЕТЧЕР ==================

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request):
    if get_user(request) != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    with engine.connect() as conn:
        reports = conn.execute(
            text("SELECT * FROM reports ORDER BY created_at DESC")
        ).mappings().all()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )
