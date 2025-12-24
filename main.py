import os
import asyncpg
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SECRET = os.getenv("SESSION_SECRET", "secret")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"])

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- STARTUP / SHUTDOWN ----------

@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        ssl="require",
    )


@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()


# ---------- HELPERS ----------

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


async def get_user(username: str):
    async with app.state.pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE username=$1",
            username
        )


def require_login(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)


# ---------- ROUTES ----------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login")
    return RedirectResponse("/dispatcher")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html>
    <head><title>Login</title></head>
    <body>
        <h2>Вход</h2>
        <form method="post">
            <input name="username" placeholder="Логин"><br>
            <input name="password" type="password" placeholder="Пароль"><br><br>
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
    user = await get_user(username)

    if not user:
        return HTMLResponse("❌ Пользователь не найден", status_code=401)

    if not verify_password(password, user["password_hash"]):
        return HTMLResponse("❌ Неверный пароль", status_code=401)

    request.session["user"] = {
        "username": user["username"],
        "role": user["role"],
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/driller", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    auth = require_login(request)
    if auth:
        return auth

    if request.session["user"]["role"] != "dispatcher":
        return HTMLResponse("⛔ Доступ запрещён", status_code=403)

    return """
    <h1>Панель диспетчера</h1>
    <p>Вы успешно вошли</p>
    <a href="/logout">Выйти</a>
    """


@app.get("/driller", response_class=HTMLResponse)
async def driller(request: Request):
    auth = require_login(request)
    if auth:
        return auth

    return """
    <h1>Форма буровика</h1>
    <p>Доступ разрешён</p>
    <a href="/logout">Выйти</a>
    """


@app.get("/db-check")
async def db_check():
    async with app.state.pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
