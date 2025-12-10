from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv
import os
import datetime
from passlib.context import CryptContext


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
FIRST_ADMIN_PASSWORD = os.getenv("FIRST_ADMIN_PASSWORD")


app = FastAPI()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


##########################################
# MODELS
##########################################
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    hashed_password = Column(String)
    role = Column(String)   # admin / worker


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    datetime = Column(DateTime, default=datetime.datetime.utcnow)
    area = Column(String)
    rig = Column(String)
    meters = Column(String)
    pogon = Column(String)
    note = Column(String)
    person = Column(String)
    op = Column(String)


Base.metadata.create_all(bind=engine)


##########################################
# startup – create first admin
##########################################
@app.on_event("startup")
def startup():
    db = SessionLocal()

    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        hashed = pwd_context.hash(FIRST_ADMIN_PASSWORD)
        db.add(User(username="admin", hashed_password=hashed, role="admin"))
        db.commit()


##########################################
# auth helpers
##########################################
def authenticate(username, password, db):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not pwd_context.verify(password, user.hashed_password):
        return None
    return user


def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == token).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=401)
    return user


##########################################
# ROUTES
##########################################

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/dispatcher")


# LOGIN
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(status_code=401)
    return {"access_token": user.username, "token_type": "bearer", "role": user.role}


# CREATE USER  (admin only)
@app.post("/create_user")
def create_user(username: str, password: str, role: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    hashed = pwd_context.hash(password)
    user = User(username=username, hashed_password=hashed, role=role)
    db.add(user)
    db.commit()
    return {"status": "ok"}


##########################################
# WORKER – submit report
##########################################
@app.post("/send")
def send_report(
        area: str = Form(...),
        rig: str = Form(...),
        meters: str = Form(...),
        pogon: str = Form(...),
        op: str = Form(...),
        person: str = Form(...),
        note: str = Form(""),
        db: Session = Depends(get_db)
):
    r = Report(area=area, rig=rig, meters=meters, pogon=pogon, op=op, person=person, note=note)
    db.add(r)
    db.commit()
    return {"message": "OK"}


##########################################
# dispatcher HTML
##########################################
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher():
    return """
    <h2>Dispatcher OK</h2>
    <p>Теперь вход работает</p>
    """
