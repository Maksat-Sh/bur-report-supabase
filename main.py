import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy import select
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from argon2 import PasswordHasher
import jwt

# -------------------- APP --------------------

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -------------------- DB ---------------------

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("startup")
async def on_start():
    await init_models()


# -------------------- MODELS ---------------------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password_hash = Column(String)
    full_name = Column(String)
    role = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    rig = Column(String)
    area = Column(String)
    meter = Column(String)
    pognometr = Column(String)
    operation = Column(String)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


argon2 = PasswordHasher()

# -------------------- AUTH ---------------------

SECRET_KEY = "supersecret"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


async def get_db():
    async with async_session() as session:
        yield session


def create_token(data: dict):
    data.update({"exp": datetime.utcnow() + timedelta(days=7)})
    return jwt.encode(data, SECRET_KEY, ALGORITHM)


async def get_current_user(token=Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(status_code=401)

    result = await db.execute(select(User).filter(User.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401)

    return user


@app.post("/token")
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401)

    try:
        argon2.verify(user.password_hash, form.password)
    except:
        raise HTTPException(status_code=401)

    return {"access_token": create_token({"sub": user.username}), "token_type": "bearer"}


# -------------------- ROUTES ---------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/report")
async def submit_report(
    username: str = Form(...),
    rig: str = Form(...),
    area: str = Form(...),
    meter: str = Form(...),
    pognometr: str = Form(...),
    operation: str = Form(...),
    comment: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    r = Report(
        username=username,
        rig=rig, area=area, meter=meter,
        pognometr=pognometr, operation=operation,
        comment=comment
    )
    db.add(r)
    await db.commit()
    return {"message": "OK"}
