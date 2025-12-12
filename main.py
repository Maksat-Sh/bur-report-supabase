import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime, timedelta
import jwt

# ==========================
# ENV
# ==========================
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# ==========================
# DATABASE
# ==========================
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# ==========================
# MODELS
# ==========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    hashed_password = Column(String)
    role = Column(String)  # admin / driller


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    section = Column(String)
    rig_number = Column(String)
    meterage = Column(String)
    pogonometr = Column(String)
    operation_type = Column(String)
    responsible = Column(String)
    note = Column(Text)


# ==========================
# SCHEMAS
# ==========================
class CreateUser(BaseModel):
    username: str
    password: str
    role: str


class CreateReport(BaseModel):
    section: str
    rig_number: str
    meterage: str
    pogonometr: str
    operation_type: str
    responsible: str
    note: str | None = None


# ==========================
# UTILS
# ==========================
def create_token(data: dict):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=12)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_db():
    async with async_session() as session:
        yield session


async def get_user_by_username(db, username):
    q = await db.execute(
        User.__table__.select().where(User.username == username)
    )
    return q.scalar_one_or_none()


def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)


def hash_password(password):
    return pwd_context.hash(password)


async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user


# ==========================
# APP
# ==========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================
# STARTUP — создаём таблицы
# ==========================
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ==========================
# AUTH
# ==========================
@app.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = await get_user_by_username(db, form.username)
    if not user:
        raise HTTPException(status_code=400, detail="Wrong username")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong password")

    token = create_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer", "role": user.role}


# ==========================
# ADMIN: создать пользователя
# ==========================
@app.post("/users/create")
async def create_user(data: CreateUser, admin=Depends(require_admin), db=Depends(get_db)):
    existing = await get_user_by_username(db, data.username)
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role
    )
    db.add(new_user)
    await db.commit()

    return {"status": "OK", "message": "User created"}


# ==========================
# БУРОВОЙ: отправить отчёт
# ==========================
@app.post("/reports")
async def add_report(report: CreateReport, user=Depends(get_current_user), db=Depends(get_db)):
    new_r = Report(**report.dict())
    db.add(new_r)
    await db.commit()
    return {"status": "OK"}


# ==========================
# ДИСПЕТЧЕР: список отчётов
# ==========================
@app.get("/reports")
async def get_reports(admin=Depends(require_admin), db=Depends(get_db)):
    q = await db.execute(Report.__table__.select().order_by(Report.id.desc()))
    return q.fetchall()
