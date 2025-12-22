import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from starlette.status import HTTP_302_FOUND
from fastapi.templating import Jinja2Templates

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

app = FastAPI()

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- DB ----------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}


# ---------- LOGIN ----------
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request}
    )


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    query = text("""
        SELECT role FROM users
        WHERE username = :u AND password = :p
    """)
    result = await db.execute(query, {"u": username, "p": password})
    user = result.fetchone()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
            status_code=400
        )

    role = user[0]

    if role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=HTTP_302_FOUND)
    else:
        return RedirectResponse("/report", status_code=HTTP_302_FOUND)


# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT id, rig_number, meters, created_at
        FROM reports
        ORDER BY created_at DESC
    """))
    reports = result.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports},
    )


# ---------- REPORT (буровик) ----------
@app.get("/report", response_class=HTMLResponse)
async def report_form():
    return HTMLResponse("<h2>Форма буровика (добавим позже)</h2>")
