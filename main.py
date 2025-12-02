from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import httpx
from passlib.context import CryptContext

app = FastAPI()

# === Настройка сессий ===
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

# === Подключение статических файлов ===
app.mount("/static", StaticFiles(directory="static"), name="static")

# === Supabase REST API ===
SUPABASE_URL = "https://ovkfakpwgvrpbnjbrkza.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92a2Zha3B3Z3ZycGJuamJya3phIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Njc5NTEyMywiZXhwIjoyMDcyMzcxMTIzfQ.PYn5uo29ucIel9XcMDXph7JDQPEfHFu0QC-axDb-774"

# === Пароли ===
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==========================
#   РАБОТА С SUPABASE
# ==========================
async def supabase_select(table: str, filters: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filters}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        print("SELECT:", url, r.status_code, r.text)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail=r.text)
        return r.json()


async def supabase_insert(table: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=data, headers=headers)
        print("INSERT:", url, r.status_code, r.text)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=r.text)
        return r.json()


# ==========================
#         ЛОГИН
# ==========================
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return open("templates/login.html", "r", encoding="utf-8").read()


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await supabase_select("users", f"username=eq.{username}")

    if not users:
        raise HTTPException(status_code=400, detail="User not found")

    user = users[0]

    # Проверка пароля
    if not pwd_context.verify(password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid password")

    # Устанавливаем сессию
    request.session["user"] = {
        "username": user["username"],
        "role": user["role"]
    }

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/bur", status_code=302)


# ==========================
#    СТРАНИЦА ДИСПЕТЧЕРА
# ==========================
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    if "user" not in request.session or request.session["user"]["role"] != "dispatcher":
        return RedirectResponse("/", status_code=302)

    return open("templates/dispatcher.html", "r", encoding="utf-8").read()


# ==========================
#    СТРАНИЦА БУРОВИКА
# ==========================
@app.get("/bur", response_class=HTMLResponse)
async def bur_page(request: Request):
    if "user" not in request.session or request.session["user"]["role"] != "bur":
        return RedirectResponse("/", status_code=302)

    return open("templates/bur.html", "r", encoding="utf-8").read()


# ==========================
#      ОТПРАВКА СВОДКИ
# ==========================
@app.post("/submit_report")
async def submit_report(
    request: Request,
    uchastok: str = Form(...),
    rig: str = Form(...),
    metrazh: str = Form(...),
    pogon: str = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form(...)
):
    if "user" not in request.session:
        raise HTTPException(status_code=403)

    await supabase_insert("reports", {
        "uchastok": uchastok,
        "rig": rig,
        "metrazh": metrazh,
        "pogon": pogon,
        "operation": operation,
        "responsible": responsible,
        "note": note
    })

    return {"message": "Report submitted successfully"}


# ==========================
#  ВЫХОД ИЗ СИСТЕМЫ
# ==========================
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
