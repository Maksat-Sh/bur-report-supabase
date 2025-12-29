from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import hashlib

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_123"
)

templates = Jinja2Templates(directory="templates")

# ======================
# ХЭШИРОВАНИЕ
# ======================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

PASSWORD_HASH_123 = hash_password("123")

# ======================
# ПОЛЬЗОВАТЕЛИ
# ======================

users = {
    "dispatcher": {
        "password": PASSWORD_HASH_123,
        "role": "dispatcher"
    },
    "bur1": {
        "password": PASSWORD_HASH_123,
        "role": "driller"
    },
    "bur2": {
        "password": PASSWORD_HASH_123,
        "role": "driller"
    }
}

# ======================
# ROOT
# ======================

@app.get("/")
def root():
    return RedirectResponse("/login")

# ======================
# LOGIN
# ======================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    user = users.get(username)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not verify_password(password, user["password"]):
        return RedirectResponse("/login", status_code=302)

    request.session["user"] = username
    request.session["role"] = user["role"]

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/reports", status_code=302)

# ======================
# LOGOUT
# ======================

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ======================
# DISPATCHER
# ======================

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    return templates.TemplateResponse("dispatcher.html", {"request": request})

# ======================
# REPORTS (БУРОВИКИ)
# ======================

@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    if request.session.get("role") != "driller":
        return RedirectResponse("/login")

    return templates.TemplateResponse("reports.html", {"request": request})
