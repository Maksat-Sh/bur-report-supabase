from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def get_user(username: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT username, password_hash, role FROM users WHERE username=%s",
        (username,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    user = get_user(username)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Пользователь не найден"}
        )

    _, password_hash, role = user

    if not verify_password(password, password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный пароль"}
        )

    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/worker", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request):
    return HTMLResponse("<h1>Диспетчер вошёл</h1>")

@app.get("/worker", response_class=HTMLResponse)
def worker(request: Request):
    return HTMLResponse("<h1>Буровик вошёл</h1>")
