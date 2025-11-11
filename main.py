from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timezone, timedelta
import io
from openpyxl import Workbook
import hashlib
import os
import urllib.parse

# --- Настройки ---
# Ожидается, что в переменных окружения задан SUPABASE_URL, например:
# postgresql://postgres:SECRET_PASSWORD@db....supabase.co:5432/postgres
SUPABASE_URL = os.environ.get("SUPABASE_URL")
if not SUPABASE_URL:
    raise RuntimeError("Не задана переменная окружения SUPABASE_URL (строка подключения к Postgres Supabase).")

# Часовой пояс отображения (UTC+5)
DISPLAY_TZ_OFFSET = 5  # целое число часов

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- SQLAlchemy ---
# Для Postgres: передаём SUPABASE_URL напрямую
DATABASE_URL = SUPABASE_URL
# Добавим параметр client_encoding через query, если нужно (обычно не нужно).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

# --- Модели ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'worker' or 'dispatcher'
    site = Column(String, nullable=True)

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    site = Column(String)
    rig_number = Column(String)
    meterage = Column(Float)
    pogonometr = Column(Float)
    operation = Column(String)
    author = Column(String)   # username
    note = Column(Text)

# Создаем таблицы (если ещё не созданы)
Base.metadata.create_all(bind=engine)

# --- Участки (единый список) ---
SITES = ["Хорасан", "Заречное", "Карамурын", "Ирколь", "Степногорск"]

# --- Утилиты ---
def get_current_user(request: Request):
    return request.session.get("user")

def utc_to_display(dt_utc: datetime) -> str:
    if dt_utc is None:
        return ""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    disp = dt_utc.astimezone(timezone(timedelta(hours=DISPLAY_TZ_OFFSET)))
    return disp.strftime("%Y-%m-%d %H:%M:%S")

# --- Создание дефолтного диспетчера, если нет ---
def ensure_default_dispatcher():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="dispatcher").first():
            u = User(
                username="dispatcher",
                full_name="Главный Диспетчер",
                password_hash=hash_password("dispatcher"),
                role="dispatcher",
                site=None
            )
            db.add(u); db.commit()
    finally:
        db.close()

ensure_default_dispatcher()

# --- Роуты ---
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=username).first()
        if not user or user.password_hash != hash_password(password):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
        # store minimal user in session
        request.session["user"] = {"username": user.username, "full_name": user.full_name, "role": user.role, "site": user.site}
        if user.role == "worker":
            return RedirectResponse("/worker_form", status_code=303)
        else:
            return RedirectResponse("/dispatcher", status_code=303)
    finally:
        db.close()

@app.get("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/login")

@app.get("/worker_form", response_class=HTMLResponse)
def worker_form(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "worker":
        return RedirectResponse("/login")
    now_display = (datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=DISPLAY_TZ_OFFSET))).strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse("worker_form.html", {"request": request, "user": user, "sites": SITES, "now": now_display})

@app.post("/submit_worker_report", response_class=HTMLResponse)
def submit_worker_report(request: Request,
                         site: str = Form(...),
                         rig_number: str = Form(...),
                         meterage: float = Form(...),
                         pogonometr: float = Form(...),
                         operation: str = Form(...),
                         note: str = Form("")):
    user = get_current_user(request)
    if not user or user.get("role") != "worker":
        return RedirectResponse("/login")
    db = SessionLocal()
    try:
        # author сохраняем как username (логин)
        author_username = user.get("username")
        # сохраняем время в UTC
        r = Report(date=datetime.now(timezone.utc), site=site, rig_number=rig_number,
                   meterage=meterage, pogonometr=pogonometr, operation=operation, author=author_username, note=note)
        db.add(r)
        db.commit()
        now_display = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=DISPLAY_TZ_OFFSET))).strftime("%Y-%m-%d %H:%M:%S")
        return templates.TemplateResponse("worker_form.html", {"request": request, "user": user, "sites": SITES, "now": now_display, "success": "Отчёт сохранён"})
    finally:
        db.close()

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_view(request: Request, site: str = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    db = SessionLocal()
    try:
        query = db.query(Report).order_by(Report.date.desc())
        if site:
            query = query.filter(Report.site == site)
        reports = query.all()
        # преобразуем дату в DISPLAY_TZ и также достаём ФИО для отображения (по username)
        # соберём map username->full_name
        usernames = {r.author for r in reports if r.author}
        users = db.query(User).filter(User.username.in_(list(usernames))).all() if usernames else []
        name_map = {u.username: u.full_name for u in users}
        display_reports = []
        for r in reports:
            display_reports.append({
                "id": r.id,
                "date": utc_to_display(r.date),
                "site": r.site,
                "rig_number": r.rig_number,
                "meterage": r.meterage,
                "pogonometr": r.pogonometr,
                "operation": r.operation,
                "author_username": r.author,
                "author_full_name": name_map.get(r.author) or "",
                "note": r.note or ""
            })
        return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": display_reports, "sites": [""] + SITES, "selected_site": site or ""})
    finally:
        db.close()

@app.get("/export_excel")
def export_excel(request: Request, site: str = None):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    db = SessionLocal()
    try:
        query = db.query(Report).order_by(Report.date.desc())
        if site:
            query = query.filter(Report.site == site)
        reports = query.all()

        wb = Workbook()
        ws = wb.active
        ws.title = "Reports"
        ws.append(["ID","Дата(UTC+5)","Участок","Номер агрегата","Метраж","Погонометр","Операция","Логин","ФИО","Примечание"])
        for r in reports:
            author_full = ""
            if r.author:
                u = db.query(User).filter_by(username=r.author).first()
                if u:
                    author_full = u.full_name or ""
            ws.append([r.id, utc_to_display(r.date), r.site, r.rig_number, r.meterage, r.pogonometr, r.operation, r.author, author_full, r.note or ""])
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
    finally:
        db.close()

@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    db = SessionLocal()
    try:
        all_users = db.query(User).all()
        return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": all_users, "sites": SITES})
    finally:
        db.close()

@app.post("/create_user")
def create_user(request: Request, username: str = Form(...), full_name: str = Form(""), password: str = Form(...), role: str = Form(...), site: str = Form(None)):
    user = get_current_user(request)
    if not user or user.get("role") != "dispatcher":
        return RedirectResponse("/login")
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=username).first():
            return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": db.query(User).all(), "sites": SITES, "error": "Пользователь уже существует"})
        u = User(username=username, full_name=full_name, password_hash=hash_password(password), role=role, site=site)
        db.add(u)
        db.commit()
        return RedirectResponse("/users", status_code=303)
    finally:
        db.close()
