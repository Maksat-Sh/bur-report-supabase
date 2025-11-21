from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Шаблоны
templates = Jinja2Templates(directory="templates")

# ВРЕМЕННАЯ ВНУТРЕННЯЯ БАЗА ПОЛЬЗОВАТЕЛЕЙ
# (пока таблица users пуста, чтобы вы могли зайти)
USERS = {
    "dispatcher": {"password": "1234", "role": "dispatcher"},
    "bur1": {"password": "123", "role": "bur"}
}

# Главная → редирект на логин
@app.get("/")
def root():
    return RedirectResponse("/login")

# Страница логина
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

# Обработка логина
@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = USERS.get(username)
    if not user or user["password"] != password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    # Если диспетчер — открываем его панель
    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)

    # Если буровик — форма буровика
    if user["role"] == "bur":
        return RedirectResponse("/burform", status_code=302)


# Интерфейс диспетчера
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})


# Форма буровика
@app.get("/burform", response_class=HTMLResponse)
def bur_form(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})

