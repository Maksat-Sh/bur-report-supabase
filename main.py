import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "ssl": True
    }
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


# ---------- LOGIN ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    q = text("""
        SELECT role FROM users
        WHERE username=:u AND password=:p
    """)
    res = await db.execute(q, {"u": username, "p": password})
    row = res.fetchone()

    if not row:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
        )

    request.session["user"] = username
    request.session["role"] = row[0]

    return RedirectResponse(
        "/dispatcher" if row[0] == "dispatcher" else "/driller",
        status_code=302,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    res = await db.execute(text("SELECT * FROM reports ORDER BY created_at DESC"))
    reports = res.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports},
    )


@app.post("/create-user")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if request.session.get("role") != "dispatcher":
        return RedirectResponse("/login")

    await db.execute(
        text("""
            INSERT INTO users (username, password, role)
            VALUES (:u, :p, :r)
        """),
        {"u": username, "p": password, "r": role},
    )
    await db.commit()
    return RedirectResponse("/dispatcher", status_code=302)


# ---------- DRILLER ----------
@app.get("/driller", response_class=HTMLResponse)
async def driller(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login")

    return templates.TemplateResponse("driller.html", {"request": request})


@app.post("/submit-report")
async def submit_report(
    request: Request,
    site: str = Form(...),
    rig: str = Form(...),
    meters: int = Form(...),
    pogonometr: int = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user"):
        return RedirectResponse("/login")

    await db.execute(
        text("""
            INSERT INTO reports
            (username, site, rig, meters, pogonometr, note)
            VALUES (:u, :s, :r, :m, :p, :n)
        """),
        {
            "u": request.session["user"],
            "s": site,
            "r": rig,
            "m": meters,
            "p": pogonometr,
            "n": note,
        },
    )
    await db.commit()
    return RedirectResponse("/driller", status_code=302)


# ---------- DB CHECK ----------
@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}
