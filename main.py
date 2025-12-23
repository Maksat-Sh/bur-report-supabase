import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

# =======================
# CONFIG
# =======================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8iur433s73btijog-a.frankfurt-postgres.render.com:6543/report_oag9?sslmode=require"
)

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

# =======================
# APP
# =======================

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# =======================
# DB
# =======================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": True,
    }
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# =======================
# ROUTES
# =======================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    with open("templates/login.html", encoding="utf-8") as f:
        return f.read()


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
    row = result.first()

    if not row:
        return PlainTextResponse("Неверный логин", status_code=401)

    if row[0] != password:
        return PlainTextResponse("Неверный пароль", status_code=401)

    request.session["user"] = username
    return RedirectResponse("/dispatcher", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)

    with open("templates/dispatcher.html", encoding="utf-8") as f:
        return f.read()


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
