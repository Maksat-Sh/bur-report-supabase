import os
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy import text

# ======================
# CONFIG
# ======================
DATABASE_URL = os.getenv("DATABASE_URL")
DISPATCHER_LOGIN = os.getenv("DISPATCHER_LOGIN", "dispatcher")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD", "1234")

# ======================
# DB
# ======================
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False
)

async def get_db():
    async with SessionLocal() as session:
        yield session

# ======================
# APP
# ======================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ======================
# ROUTES
# ======================

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Проверка подключения к БД (важно!)
    await db.execute(text("select 1"))

    if username == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        return RedirectResponse("/dispatcher", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": "Неверный логин или пароль"
        }
    )

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    return HTMLResponse("<h1>Диспетчерская работает ✅</h1>")
