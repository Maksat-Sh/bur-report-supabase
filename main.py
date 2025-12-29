from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

templates = Jinja2Templates(directory="templates")

# =========================
# ВРЕМЕННАЯ БАЗА ПОЛЬЗОВАТЕЛЕЙ
# пароль у всех: 123
# =========================
USERS = {
    "dispatcher": {
        "username": "dispatcher",
        "password": "123",
        "role": "dispatcher"
    },
    "bur1": {
        "username": "bur1",
        "password": "123",
        "role": "bur"
    },
    "bur2": {
        "username": "bur2",
        "password": "123",
        "role": "bur"
    }
}


# =========================
# ГЛАВНАЯ
# =========================
@app.get("/")
def root():
    return RedirectResponse("/login")


# =========================
# LOGIN
# =========================
@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    user = USERS.get(username)

    if not user or user["password"] != password:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Неверный логин или пароль"
            }
        )

    request.session["user"] = {
        "username": user["username"],
        "role": user["role"]
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/reports", status_code=302)


# =========================
# LOGOUT
# =========================
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# =========================
# DISPATCHER
# =========================
@app.get("/dispatcher")
def dispatcher(request: Request):
    user = request.session.get("user")

    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "user": user
    })


# =========================
# REPORTS (БУРОВИКИ)
# =========================
@app.get("/reports")
def reports(request: Request):
    user = request.session.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "user": user
    })
