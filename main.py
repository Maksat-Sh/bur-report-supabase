from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SUPER_SECRET_KEY")

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ======================
# ПОЛЬЗОВАТЕЛИ
# ======================
users = {
    "dispatcher": {
        "username": "dispatcher",
        "password": pwd_context.hash("123"),
        "role": "dispatcher"
    },
    "bur1": {
        "username": "bur1",
        "password": pwd_context.hash("123"),
        "role": "bur"
    },
    "bur2": {
        "username": "bur2",
        "password": pwd_context.hash("123"),
        "role": "bur"
    }
}

# ======================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_current_user(request: Request):
    return request.session.get("user")

# ======================
# ROUTES
# ======================
@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

# ---------- LOGIN ----------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = users.get(username)

    if not user or not verify_password(password, user["password"]):
        return RedirectResponse("/login", status_code=302)

    request.session["user"] = {
        "username": user["username"],
        "role": user["role"]
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/bur", status_code=302)

# ---------- LOGOUT ----------
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "dispatcher":
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": user}
    )

# ---------- BUR ----------
@app.get("/bur", response_class=HTMLResponse)
def bur(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "bur":
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "bur.html",
        {"request": request, "user": user}
    )
