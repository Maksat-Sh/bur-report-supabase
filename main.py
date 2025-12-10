import os
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ================== DB =====================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

# ================== PASSWORDS ==============

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ================== MODELS =================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)  # admin or worker


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    datetime = Column(DateTime, default=datetime.utcnow)
    site = Column(String)
    rig = Column(String)
    meters = Column(String)
    pognometr = Column(String)
    operation = Column(String)
    person = Column(String)
    note = Column(Text)


Base.metadata.create_all(bind=engine)


# ========== create default admin ==============

def create_admin():
    db = SessionLocal()
    admin = db.query(User).filter_by(role="admin").first()
    if admin is None:
        login = os.getenv("ADMIN_LOGIN", "admin")
        pwd_raw = os.getenv("ADMIN_PASSWORD", "admin")

        hashed = pwd.hash(pwd_raw)

        new_admin = User(
            username=login,
            password=hashed,
            role="admin"
        )
        db.add(new_admin)
        db.commit()
    db.close()

create_admin()


# ================== FASTAPI ==================

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# ============= AUTH =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def auth_required(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)


# ================== ROUTES ===================

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return open("templates/login.html", encoding="utf8").read()


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user or not pwd.verify(password, user.password):
        return HTMLResponse("<h3>Неправильные логин или пароль</h3>")

    request.session = {"user": user.username, "role": user.role}

    if user.role == "admin":
        return RedirectResponse("/dispatcher", status_code=302)
    return RedirectResponse("/burform", status_code=302)


@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    if not request.session or request.session.get("role") != "admin":
        return RedirectResponse("/login")

    return open("templates/dispatcher.html", encoding="utf8").read()


@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    return open("templates/burform.html", encoding="utf8").read()


# ====== API add user (admin can create users) ======

@app.post("/create_user")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: SessionLocal = Depends(get_db)
):

    if request.session.get("role") != "admin":
        return {"error": "only admin"}

    hashed = pwd.hash(password)

    user = User(username=username, password=hashed, role="worker")
    db.add(user)
    db.commit()
    return {"message": "ok"}


# ========= submit report =====================

@app.post("/submit")
async def submit(
    site: str = Form(...),
    rig: str = Form(...),
    meters: str = Form(...),
    pognometr: str = Form(...),
    operation: str = Form(...),
    person: str = Form(...),
    note: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    r = Report(
        site=site,
        rig=rig,
        meters=meters,
        pognometr=pognometr,
        operation=operation,
        person=person,
        note=note
    )
    db.add(r)
    db.commit()

    return {"message": "ok"}
