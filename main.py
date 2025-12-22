import os
from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"ssl": "require"}  # ВАЖНО для Supabase
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

app = FastAPI()

# ---------- DB SESSION ----------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ---------- DB CHECK ----------
@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "detail": str(e)}

# ---------- LOGIN ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <form method="post">
        <input name="login" placeholder="Логин"><br>
        <input name="password" type="password" placeholder="Пароль"><br>
        <button type="submit">Войти</button>
    </form>
    """

@app.post("/login")
async def login(
    login: str = Form(...),
    password: str = Form(...)
):
    # ПРОСТАЯ логика, без токенов
    if login == "dispatcher" and password == "1234":
        response = RedirectResponse("/dispatcher", status_code=302)
        response.set_cookie("auth", "yes")
        return response
    raise HTTPException(status_code=401, detail="Неверный логин или пароль")

def dispatcher_only(request: Request):
    if request.cookies.get("auth") != "yes":
        raise HTTPException(status_code=403, detail="Нет доступа")

# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    dispatcher_only(request)

    result = await db.execute(
        text("SELECT id, date_time, rig_number, meters, note FROM reports ORDER BY date_time DESC")
    )
    rows = result.fetchall()

    html = "<h2>Сводки буровиков</h2><table border=1>"
    for r in rows:
        html += f"<tr><td>{r.id}</td><td>{r.date_time}</td><td>{r.rig_number}</td><td>{r.meters}</td><td>{r.note}</td></tr>"
    html += "</table>"

    return html

# ---------- ROOT ----------
@app.get("/")
async def root():
    return {"status": "ok"}
