import os
import psycopg2
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def verify_password(password, hash):
    return pwd_context.verify(password, hash)

# ---------- LOGIN ----------
@app.get("/login", response_class=HTMLResponse)
def login_page():
    return """
    <h2>Вход</h2>
    <form method="post">
      <input name="username" placeholder="Логин"><br>
      <input name="password" type="password" placeholder="Пароль"><br>
      <button>Войти</button>
    </form>
    """

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT password_hash, role FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close()
    db.close()

    if not row or not verify_password(password, row[0]):
        return HTMLResponse("Неверный логин или пароль", status_code=401)

    request.session["user"] = username
    request.session["role"] = row[1]

    return RedirectResponse("/reports", status_code=302)

# ---------- ОТПРАВКА СВОДКИ ----------
@app.get("/submit", response_class=HTMLResponse)
def submit_form():
    return """
    <h2>Сводка буровика</h2>
    <form method="post">
      Бур: <input name="bur"><br>
      Участок: <input name="uchastok"><br>
      Метраж: <input name="metraj" type="number"><br>
      Погонометр: <input name="pogonometr" type="number"><br>
      Примечание: <input name="note"><br>
      <button>Отправить</button>
    </form>
    """

@app.post("/submit")
def submit(
    request: Request,
    bur: str = Form(...),
    uchastok: str = Form(...),
    metraj: int = Form(...),
    pogonometr: int = Form(...),
    note: str = Form("")
):
    if request.session.get("role") != "bur":
        return HTMLResponse("Доступ запрещён", status_code=403)

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO reports (bur, uchastok, metraj, pogonometr, note)
        VALUES (%s,%s,%s,%s,%s)
    """, (bur, uchastok, metraj, pogonometr, note))
    db.commit()
    cur.close()
    db.close()

    return HTMLResponse("Сводка отправлена")

# ---------- ПРОСМОТР СВОДОК ----------
@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT id, created_at, bur, uchastok, metraj, pogonometr, note
        FROM reports ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()

    html = """
    <h2>Сводки</h2>
    <table border=1>
    <tr>
      <th>ID</th><th>Дата</th><th>Бур</th><th>Участок</th>
      <th>Метраж</th><th>Погонометр</th><th>Примечание</th>
    </tr>
    """
    for r in rows:
        html += f"<tr>{''.join(f'<td>{x}</td>' for x in r)}</tr>"
    html += "</table>"
    return html
