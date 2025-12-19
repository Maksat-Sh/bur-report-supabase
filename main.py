from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND

app = FastAPI()

# 🔐 Секрет для cookie (ЛЮБОЙ, но длинный)
app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_CHANGE_ME",
)

# =========================
# НАСТРОЙКИ ДИСПЕТЧЕРА
# =========================
DISPATCHER_LOGIN = "dispatcher"
DISPATCHER_PASSWORD = "1234"


# =========================
# ПРОВЕРКА АВТОРИЗАЦИИ
# =========================
def require_login(request: Request):
    if not request.session.get("user"):
        raise RedirectResponse("/login", status_code=HTTP_302_FOUND)


# =========================
# LOGIN PAGE
# =========================
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html>
    <head>
        <title>Вход диспетчера</title>
    </head>
    <body>
        <h2>Вход диспетчера</h2>
        <form method="post">
            <input name="login" placeholder="Логин" required><br><br>
            <input name="password" type="password" placeholder="Пароль" required><br><br>
            <button type="submit">Войти</button>
        </form>
    </body>
    </html>
    """


@app.post("/login")
async def login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...)
):
    if login == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        request.session["user"] = login
        return RedirectResponse("/dispatcher", status_code=HTTP_302_FOUND)

    return HTMLResponse(
        "<h3>Неверный логин или пароль</h3><a href='/login'>Назад</a>",
        status_code=401
    )


# =========================
# LOGOUT
# =========================
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=HTTP_302_FOUND)


# =========================
# DISPATCHER PAGE
# =========================
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=HTTP_302_FOUND)

    return """
    <html>
    <head>
        <title>Диспетчер</title>
    </head>
    <body>
        <h2>Панель диспетчера</h2>
        <p>Вы вошли как диспетчер</p>
        <a href="/logout">Выйти</a>
    </body>
    </html>
    """


# =========================
# ROOT
# =========================
@app.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dispatcher", status_code=HTTP_302_FOUND)
    return RedirectResponse("/login", status_code=HTTP_302_FOUND)
