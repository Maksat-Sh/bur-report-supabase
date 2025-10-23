from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os, bcrypt, tempfile, pandas as pd
# main.py (вверху)
import os
from dotenv import load_dotenv
load_dotenv()

from supabase_client import insert_report, get_user_by_username, select_reports, get_users, insert_user
import bcrypt
import requests

from database import SessionLocal, Base, engine

from sqlalchemy.orm import declarative_base
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    date_time = Column(DateTime, default=datetime.utcnow)
    site = Column(String)
    rig = Column(String)
    xrvs = Column(String)
    metr = Column(String)
    diameter = Column(String)
    operation = Column(String)
    mbu = Column(String)
    responsible = Column(String)
    driller = Column(String)
    pogonomet = Column(String)
    note = Column(Text)

Base.metadata.create_all(bind=engine)
def get_current_user(request: Request):
    username = request.cookies.get("user")
    if not username:
        return None
    return get_user_by_username(username)


def init_users():
    db = SessionLocal()
    try:
        users = [
            ("bur1","123","Бурильщик 1","driller"),
            ("bur2","123","Бурильщик 2","driller"),
            ("dispatcher","dispatch123","Диспетчер","dispatcher"),
            ("admin","9999","Администратор","admin")
        ]
        for u, p, fn, role in users:
            if not db.query(User).filter(User.username == u).first():
                ph = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                db.add(User(username=u, password_hash=ph, full_name=fn, role=role))
        db.commit()
    except Exception as e:
        print("init_users error:", e)
    finally:
        db.close()

init_users()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session):
    username = request.cookies.get("user")
    if not username:
        return None
    return db.query(User).filter(User.username==username).first()

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login_action(request: Request, response: Response, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username==username).first()
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error":"Неверный логин или пароль"})
    ok = False
    try:
        ok = bcrypt.checkpw(password.encode(), user.password_hash.encode())
    except Exception:
        ok = False
    if not ok:
        return templates.TemplateResponse("login.html", {"request": request, "error":"Неверный логин или пароль"})
    resp = RedirectResponse(url="/form" if user.role=="driller" else "/dispatcher", status_code=302)
    resp.set_cookie(key="user", value=user.username, httponly=True)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("user")
    return resp

@app.get("/form", response_class=HTMLResponse)
def show_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role!="driller":
        return RedirectResponse("/login")
    now = (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse("form.html", {"request": request, "now": now, "driller": user.full_name or user.username})

@app.post("/submit", response_class=HTMLResponse)
def submit_form(request: Request,
                date_time: str = Form(...),
                site: str = Form(...),
                rig: str = Form(...),
                xrvs: str = Form(None),
                metr: str = Form(None),
                diameter: str = Form(None),
                operation: str = Form(None),
                pogonomet: str = Form(None),
                note: str = Form(None)):
    # получаем текущего пользователя
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    # driller fullname из user (авто)
    driller_name = user.get("full_name") or user.get("username")

    try:
        dt = datetime.fromisoformat(date_time)
    except Exception:
        dt = datetime.utcnow()

    payload = {
        "date_time": dt.isoformat(),
        "site": site,
        "rig": rig,
        "xrvs": xrvs or "",
        "metr": metr or "",
        "diameter": diameter or "",
        "operation": operation or "",
        "mbu": driller_name,      # МБУ/Ответственное лицо авто
        "driller": driller_name,
        "pogonomet": pogonomet or "",
        "note": note or ""
    }
    try:
        insert_report(payload)
    except Exception as e:
        # логируем и показываем ошибку
        return templates.TemplateResponse("form.html", {"request": request, "error": f"Ошибка при сохранении: {e}", "now": (datetime.utcnow()+timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"), "driller": driller_name})
    return templates.TemplateResponse("form.html", {"request": request, "message":"Сводка отправлена", "now": (datetime.utcnow()+timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"), "driller": driller_name})


@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role!="dispatcher":
        return RedirectResponse("/login")
    return templates.TemplateResponse("dispatcher.html", {"request": request})

from fastapi import Query
@app.get("/api/reports")
def api_reports(date: str | None = Query(None), rig: str | None = Query(None)):
    # вызов select_reports с фильтрами (PostgREST query)
    params = {}
    if date:
        # postgrest фильтрация может быть по диапазону; проще получить все и фильтровать в коде:
        # но можно использовать filter: date_time=gte.2025-10-01T00:00:00
        # для простоты: получим все и фильтруем в Python
        pass
    try:
        items = select_reports()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    out = []
    for r in items:
        dt = r.get("date_time")
        if dt:
            try:
                dt_obj = datetime.fromisoformat(dt)
                dt_str = (dt_obj + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_str = dt
        else:
            dt_str = ""
        out.append({
            "id": r.get("id"),
            "datetime": dt_str,
            "site": r.get("site"),
            "rig": r.get("rig"),
            "xrvs": r.get("xrvs"),
            "metr": r.get("metr"),
            "diameter": r.get("diameter"),
            "operation": r.get("operation"),
            "driller": r.get("driller"),
            "mbu": r.get("mbu"),
            "pogonomet": r.get("pogonomet"),
            "note": r.get("note")
        })
    # простой фильтр по rig/date если нужны
    if rig:
        out = [o for o in out if rig.lower() in (o["rig"] or "").lower()]
    if date:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            out = [o for o in out if o["datetime"] and datetime.strptime(o["datetime"], "%Y-%m-%d %H:%M:%S").date() == date_obj]
        except Exception:
            pass
    return out


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role!="dispatcher":
        return RedirectResponse("/login")
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users})

@app.post("/admin/users")
def admin_create_user(request: Request, username: str = Form(...), password: str = Form(...), full_name: str = Form(None), role: str = Form(...), db: Session = Depends(get_db)):
    current = get_current_user(request, db)
    if not current or current.role!="dispatcher":
        raise HTTPException(status_code=403, detail="Forbidden")
    if db.query(User).filter(User.username==username).first():
        users = db.query(User).order_by(User.username).all()
        return templates.TemplateResponse("admin_users.html", {"request": request, "users": users, "error":"Логин уже существует"})
    ph = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.add(User(username=username, password_hash=ph, full_name=full_name, role=role))
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/users/delete")
def admin_delete_user(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    current = get_current_user(request, db)
    if not current or current.role!="dispatcher":
        raise HTTPException(status_code=403, detail="Forbidden")
    target = db.query(User).filter(User.id==user_id).first()
    if not target:
        return RedirectResponse("/admin/users", status_code=303)
    db.delete(target)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.get("/export", response_class=FileResponse)
def export_excel(db: Session = Depends(get_db), request: Request = None):
    username = request.cookies.get("user") if request else None
    user = None
    if username:
        with SessionLocal() as s:
            user = s.query(User).filter(User.username==username).first()
    if not user or user.role!="dispatcher":
        raise HTTPException(status_code=403, detail="Forbidden")
    items = db.query(Report).order_by(Report.date_time.desc()).all()
    rows = []
    for r in items:
        rows.append({
            "ID": r.id,
            "Дата и время (UTC+5)": (r.date_time + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S") if r.date_time else "",
            "Участок": r.site,
            "Буровая": r.rig,
            "XRVS": r.xrvs,
            "Метраж": r.metr,
            "Диаметр": r.diameter,
            "Вид операции": r.operation,
            "МБУ": r.mbu,
            "Ответственный": r.responsible,
            "Бурильщик": r.driller,
            "Погонометр": r.pogonomet,
            "Примечание": r.note
        })
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.close()
    df.to_excel(tmp.name, index=False, engine="openpyxl")
    return FileResponse(path=tmp.name, filename="reports.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

