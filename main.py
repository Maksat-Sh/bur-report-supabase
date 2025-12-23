from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


async def get_db():
    async with SessionLocal() as session:
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
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT role FROM users
        WHERE username = :u AND password = :p
    """)
    result = await db.execute(query, {"u": username, "p": password})
    user = result.fetchone()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )

    if user.role == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/driller", status_code=302)


# ---------- DISPATCHER ----------
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, date_time, rig_number, meters, note FROM reports ORDER BY date_time DESC")
    )
    reports = result.fetchall()

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "reports": reports}
    )


# ---------- DRILLER ----------
@app.get("/driller", response_class=HTMLResponse)
async def driller_page(request: Request):
    return templates.TemplateResponse("driller.html", {"request": request})


@app.post("/driller")
async def submit_report(
    rig_number: str = Form(...),
    meters: int = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    await db.execute(
        text("""
            INSERT INTO reports (date_time, rig_number, meters, note)
            VALUES (NOW(), :rig, :meters, :note)
        """),
        {"rig": rig_number, "meters": meters, "note": note}
    )
    await db.commit()
    return RedirectResponse("/driller", status_code=302)


# ---------- DB CHECK ----------
@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
