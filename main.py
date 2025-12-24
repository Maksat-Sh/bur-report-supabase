import os
import asyncpg
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

app = FastAPI()

# ===== Middleware =====
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# ===== Static =====
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===== Password hashing (БЕЗ bcrypt) =====
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"])

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# ===== DB =====
@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(
        DATABASE_URL,
        ssl="require"
    )

@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()

# ===== Utils =====
async def get_user(username: str):
    async with app.state.pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT username, password_hash, role FROM users WHERE username=$1",
            username
        )

# ===== Routes =====
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
    password: str = Form(...)
):
    user = await get_user(username)

    if not user:
        return HTMLResponse("❌ Пользователь не найден", status_code=401)

    if not verify_password(password, user["password_hash"]):
        return HTMLResponse("❌ Неверный пароль", status_code=401)

    request.session["user"] = {
        "username": user["username"],
        "role": user["role"]
    }

    return RedirectResponse("/dispatcher", status_code=302)

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    with open("templates/dispatcher.html", encoding="utf-8") as f:
        html = f.read()

    return html.replace("{{username}}", user["username"])

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/db-check")
async def db_check():
    async with app.state.pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
