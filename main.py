from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os

# ---------------------- SETTINGS ------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8iur433s73btijog-a/report_oag9"
)

SECRET_KEY = "supersecret123456"   # для сессий

# ---------------------- APP INIT ------------------------

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")

# ---------------------- DATABASE ------------------------

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    datetime = Column(DateTime, default=datetime.utcnow)
    section = Column(String)
    rig_number = Column(String)
    meterage = Column(String)
    pogon = Column(String)
    operation = Column(String)
    person = Column(String)
    note = Column(String)

Base.metadata.create_all(bind=engine)

# ---------------------- USERS ------------------------

USERS = {
    "dispatcher": {"password": "1234", "role": "dispatcher"},
    "bur1": {"password": "123", "role": "driller"},
    "bur2": {"password": "123", "role": "driller"},
}

# ---------------------- HELPERS ------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_login(request: Request):
    if "user" not in request.session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return request.session["user"]


# ---------------------- ROUTES ------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("/login")


# ---------------------- LOGIN ------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username not in USERS:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин"})

    if USERS[username]["password"] != password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

    request.session["user"] = {
        "username": username,
        "role": USERS[username]["role"]
    }

    if USERS[username]["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)


# ---------------------- LOGOUT ------------------------

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------------------- DRILLER FORM ------------------------

@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request, user=Depends(require_login)):
    if user["role"] != "driller":
        return RedirectResponse("/dispatcher")

    return templates.TemplateResponse("burform.html", {"request": request})


@app.post("/submit_report")
async def submit_report(
        request: Request,
        section: str = Form(...),
        rig_number: str = Form(...),
        meterage: str = Form(...),
        pogon: str = Form(...),
        operation: str = Form(...),
        person: str = Form(...),
        note: str = Form(""),
        db=Depends(get_db)
):
    report = Report(
        section=section,
        rig_number=rig_number,
        meterage=meterage,
        pogon=pogon,
        operation=operation,
        person=person,
        note=note
    )
    db.add(report)
    db.commit()

    return templates.TemplateResponse("burform.html", {
        "request": request,
        "success": "Сводка отправлена!"
    })


# ---------------------- DISPATCHER PANEL ------------------------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_panel(request: Request, db=Depends(get_db), user=Depends(require_login)):
    if user["role"] != "dispatcher":
        return RedirectResponse("/burform")

    reports = db.query(Report).order_by(Report.datetime.desc()).all()

    return templates.TemplateResponse("dispatcher.html", {
        "request": request,
        "reports": reports
    })


# ---------------------- EXPORT ------------------------

@app.get("/export_excel")
async def export_excel(db=Depends(get_db), user=Depends(require_login)):
    if user["role"] != "dispatcher":
        raise HTTPException(403)

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Reports"

    ws.append(["ID", "Дата/время", "Участок", "№ агрегата", "Метраж", "Погонометр", "Операции", "Ответственный", "Примечание"])

    rows = db.query(Report).all()
    for r in rows:
        ws.append([
            r.id, r.datetime, r.section, r.rig_number,
            r.meterage, r.pogon, r.operation, r.person, r.note
        ])

    filepath = "/tmp/reports.xlsx"
    wb.save(filepath)

    from fastapi.responses import FileResponse
    return FileResponse(filepath, media_type="application/vnd.ms-excel", filename="reports.xlsx")
