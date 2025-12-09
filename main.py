from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime, timedelta
import jwt
from argon2 import PasswordHasher
import os
from fastapi.staticfiles import StaticFiles

# ---- ВАЖНО ----
app = FastAPI()

# только ПОСЛЕ app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
<form method="post" action="/token">

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()
argon2 = PasswordHasher()

SECRET_KEY = "supersecret"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

app = FastAPI()

templates = Jinja2Templates(directory="templates")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    full_name = Column(String)
    role = Column(String)
    password_hash = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    full_name = Column(String)
    rig = Column(String)
    area = Column(String)
    meter = Column(String)
    pognometr = Column(String)
    operation = Column(String)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


async def get_db():
    async with async_session() as session:
        yield session


def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(days=5)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return user
    except:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    try:
        argon2.verify(user.password_hash, form_data.password)
    except:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    rows = result.scalars().all()
    return templates.TemplateResponse("reports.html", {"request": request, "user": user, "reports": rows})


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "dispatcher":
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(select(User).order_by(User.id))
    rows = result.scalars().all()
    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": rows})


@app.post("/users/create")
async def create_user(
    username: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current.role != "dispatcher":
        raise HTTPException(status_code=403)

    hash = argon2.hash(password)

    user = User(
        username=username,
        full_name=full_name,
        role=role,
        password_hash=hash,
    )
    db.add(user)
    await db.commit()

    return RedirectResponse("/users", status_code=302)


@app.post("/report")
async def submit_report(
    username: str = Form(...),
    full_name: str = Form(...),
    rig: str = Form(...),
    area: str = Form(...),
    meter: str = Form(...),
    pognometr: str = Form(...),
    operation: str = Form(...),
    comment: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    report = Report(
        username=username,
        full_name=full_name,
        rig=rig,
        area=area,
        meter=meter,
        pognometr=pognometr,
        operation=operation,
        comment=comment,
    )
    db.add(report)
    await db.commit()

    return {"message": "OK"}
