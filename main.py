from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

app = FastAPI()

templates = Jinja2Templates(directory="templates")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    rig = Column(String)
    site = Column(String)
    meters = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or user.password != form_data.password:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")

    token = jwt.encode({"sub": user.username}, "secret", algorithm="HS256")

    return {"access_token": token, "token_type": "bearer"}


@app.get("/", response_class=HTMLResponse)
def dispatcher(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})
