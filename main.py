import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def verify_password(password, hash):
    return pwd_context.verify(password, hash)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        role = request.session["role"]
        return RedirectResponse(f"/{role}", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return open("templates/login.html", encoding="utf-8").read()


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    q = text("""
        SELECT username, role, password_hash
        FROM users
        WHERE username = :u
    """)
    result = await db.execute(q, {"u": username})
    user = result.fetchone()

    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse("Неверный логин или пароль", status_code=401)

    request.session["user"] = user.username
    request.session["role"] = user.role

    return RedirectResponse("/", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login", status_code=302)
    return "<h1>Диспетчер</h1><a href='/logout'>Выйти</a>"


@app.get("/driller", response_class=HTMLResponse)
async def driller(request: Request):
    if request.session.get("role") != "driller":
        return RedirectResponse("/login", status_code=302)
    return "<h1>Буровик</h1><a href='/logout'>Выйти</a>"


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}
