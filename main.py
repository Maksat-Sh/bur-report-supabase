import os
import asyncpg
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- DB ----------
async def get_conn():
    return await asyncpg.connect(DATABASE_URL)


# ---------- UTILS ----------
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------- ROUTES ----------
@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html>
    <head><title>Login</title></head>
    <body>
        <h2>Вход</h2>
        <form method="post">
            <input name="username" placeholder="Логин" required><br>
            <input name="password" type="password" placeholder="Пароль" required><br>
            <button type="submit">Войти</button>
        </form>
    </body>
    </html>
    """


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    conn = await get_conn()
    try:
        user = await conn.fetchrow(
            "SELECT id, username, password_hash, role FROM users WHERE username=$1",
            username
        )
    finally:
        await conn.close()

    if not user:
        return HTMLResponse("Неверный логин", status_code=401)

    if not verify_password(password, user["password_hash"]):
        return HTMLResponse("Неверный пароль", status_code=401)

    request.session["user_id"] = user["id"]
    request.session["role"] = user["role"]

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/driller", status_code=302)


@app.get("/dispatcher")
async def dispatcher(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    return HTMLResponse("<h1>Панель диспетчера</h1>")


@app.get("/driller")
async def driller(request: Request):
    if request.session.get("role") != "driller":
        return RedirectResponse("/login")

    return HTMLResponse("<h1>Форма буровика</h1>")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/db-check")
async def db_check():
    try:
        conn = await get_conn()
        await conn.execute("SELECT 1")
        await conn.close()
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
