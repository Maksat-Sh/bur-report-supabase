from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

import os

# =========================
# НАСТРОЙКИ
# =========================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME"
)

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

# =========================
# APP
# =========================

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# =========================
# DATABASE
# =========================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": "require"   # 🔥 ВАЖНО: решает SSL ошибку
    }
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# =========================
# ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    q = text("""
        SELECT password
        FROM users
        WHERE username = :u
    """)

    result = await db.execute(q, {"u": username})
    row = result.fetchone()

    if not row or row[0] != password:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Неверный логин или пароль"
            }
        )

    request.session["user"] = username
    return RedirectResponse("/dispatcher", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

    q = text("""
        SELECT id, created_at, site, rig_number, meters, pogonometr, operation, responsible, note
        FROM reports
        ORDER BY created_at DESC
    """)

    result = await db.execute(q)
    reports = result.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {
            "request": request,
            "reports": reports
        }
    )


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
