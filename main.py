from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta
# Казахстан UTC+6, если у вас UTC+5 — поставьте +5
timestamp = datetime.utcnow() + timedelta(hours=6)
import io
from openpyxl import Workbook
import hashlib
import os

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change")
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# SQLite local DB
DATABASE_URL = "sqlite:///./reports.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

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
    date = Column(DateTime, default=datetime.utcnow)
    site = Column(String)
    rig_number = Column(String)
    meterage = Column(Float)
    pogonometr = Column(Float)
    operation = Column(String)
    author = Column(String)
    note = Column(Text)

Base.metadata.create_all(bind=engine)

# Create a default dispatcher if none exists
def ensure_default_dispatcher():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="dispatcher").first():
            u = User(username="dispatcher", full_name="Главный Диспетчер", password_hash=hash_password("dispatcher"), role="dispatcher")
            db.add(u)
            db.commit()
    finally:
        db.close()

ensure_default_dispatcher()

def get_current_user(request: Request):
    user = request.session.get("user")
    return user

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
    # possible sites (could be read from DB or config); simple list for dropdown
    sites = ["Хорасан", "Заречное", "Карамурын", "Ирколь", "Степногорск"]
    return templates.TemplateResponse("worker_form.html", {"request": request, "user": user, "sites": sites, "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")})

@app.post("/submit_worker_report")
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
        r = Report(date=datetime.utcnow(), site=site, rig_number=rig_number, meterage=meterage, pogonometr=pogonometr, operation=operation, author=user.get("fullname"), note=note)
        db.add(r)
        db.commit()
        return templates.TemplateResponse("worker_form.html", {"request": request, "user": user, "sites": ["Участок A","Участок B","Участок C"], "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "success": "Отчёт сохранён"})
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
        sites = ["", "Участок A", "Участок B", "Участок C"]
        return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports, "sites": sites, "selected_site": site or ""})
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
        ws.append(["ID","Дата","Участок","Номер агрегата","Метраж","Погонометр","Операция","Ответственный","Примечание"])
        for r in reports:
            ws.append([r.id, r.date.strftime("%Y-%m-%d %H:%M:%S"), r.site, r.rig_number, r.meterage, r.pogonometr, r.operation, r.author, r.note or ""])
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
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
        sites = ["Участок A","Участок B","Участок C"]
        return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": all_users, "sites": sites})
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
            return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": db.query(User).all(), "sites": ["Участок A","Участок B","Участок C"], "error": "Пользователь уже существует"})
        u = User(username=username, full_name=full_name, password_hash=hashlib.sha256(password.encode('utf-8')).hexdigest(), role=role, site=site)
        db.add(u)
        db.commit()
        return RedirectResponse("/users", status_code=303)
    finally:
        db.close()
