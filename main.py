from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
from fastapi.templating import Jinja2Templates
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "dispatcher")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# ---------------- Models ---------------- #

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    datetime = Column(DateTime, default=datetime.utcnow)
    area = Column(String)
    rig = Column(String)
    depth = Column(String)
    pogon = Column(String)
    operation = Column(String)
    person = Column(String)
    note = Column(String)

Base.metadata.create_all(bind=engine)

# ---------------- APP ---------------- #

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------- LOGIN ------------ #

@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        response = RedirectResponse("/dispatcher", status_code=302)
        response.set_cookie("auth", "1")
        return response
    raise HTTPException(status_code=401, detail="Wrong login")


def auth_required(request: Request):
    if request.cookies.get("auth") != "1":
        raise HTTPException(status_code=401)
    return True


# -------- BUR FORM -------- #

@app.get("/bur", response_class=HTMLResponse)
def bur_form(request: Request):
    return templates.TemplateResponse("bur.html", {"request": request})


@app.post("/bur")
def bur_send(
    area: str = Form(...),
    rig: str = Form(...),
    depth: str = Form(...),
    pogon: str = Form(...),
    operation: str = Form(...),
    person: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    report = Report(
        area=area,
        rig=rig,
        depth=depth,
        pogon=pogon,
        operation=operation,
        person=person,
        note=note,
    )
    db.add(report)
    db.commit()
    return RedirectResponse("/bur", status_code=302)


# -------- DISPATCHER -------- #

@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher(request: Request, db: Session = Depends(get_db), auth=Depends(auth_required)):
    reports = db.query(Report).order_by(Report.id.desc()).all()
    return templates.TemplateResponse("dispatcher.html", {"request": request, "reports": reports})

