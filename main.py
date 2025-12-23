import os
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},  # ← ВАЖНО для Supabase
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Проверка подключения
    await db.execute(text("select 1"))

    query = text("""
        SELECT role FROM users
        WHERE username = :u AND password = :p
    """)
    result = await db.execute(query, {"u": username, "p": password})
    user = result.first()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
        )

    if user.role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    if user.role == "driller":
        return RedirectResponse("/driller", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неизвестная роль"},
    )


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher():
    return HTMLResponse("<h1>Диспетчер</h1>")


@app.get("/driller", response_class=HTMLResponse)
async def driller():
    return HTMLResponse("<h1>Буровик</h1>")
