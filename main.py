import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": "require"}  # ← ВАЖНО
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")


# ---------- DB CHECK ----------
@app.get("/db-check")
async def db_check():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return {"db": "ok", "result": result.scalar()}
    except Exception as e:
        return {"db": "error", "detail": str(e)}


# ---------- LOGIN ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    # ПРОСТОЙ диспетчер (без токенов)
    if username == "dispatcher" and password == "1234":
        request.session["dispatcher"] = True
        return RedirectResponse("/dispatcher", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"}
    )


# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not request.session.get("dispatcher"):
        return RedirectResponse("/login", status_code=302)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, date_time, rig_number, meters, note
                FROM reports
                ORDER BY date_time DESC
            """)
        )
        reports = result.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )


# ---------- ROOT ----------
@app.get("/")
async def root():
    return RedirectResponse("/login")
