import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ======================
# DB CHECK
# ======================
@app.get("/db-check")
async def db_check():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"db": "ok"}


# ======================
# AUTH (простая)
# ======================
DISPATCHER_LOGIN = "dispatcher"
DISPATCHER_PASSWORD = "1234"


def is_logged_in(request: Request):
    return request.cookies.get("dispatcher") == "1"


# ======================
# ROOT
# ======================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dispatcher", status_code=302)


# ======================
# LOGIN
# ======================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...)
):
    if username == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        response = RedirectResponse("/dispatcher", status_code=302)
        response.set_cookie("dispatcher", "1", httponly=True)
        return response

    raise HTTPException(status_code=401, detail="Неверный логин или пароль")


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("dispatcher")
    return response


# ======================
# DISPATCHER
# ======================
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request}
    )


# ======================
# STARTUP
# ======================
@app.on_event("startup")
async def startup():
    print("🚀 Application started")
