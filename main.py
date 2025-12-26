from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def verify_password(password, hash):
    return pwd_context.verify(password, hash)

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT password_hash, role FROM users WHERE username=%s",
        (username,)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user:
        return RedirectResponse("/login", status_code=302)

    password_hash, role = user

    if not verify_password(password, password_hash):
        return RedirectResponse("/login", status_code=302)

    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    return RedirectResponse("/driller", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})

@app.get("/driller", response_class=HTMLResponse)
def driller_page(request: Request):
    return templates.TemplateResponse("driller.html", {"request": request})
