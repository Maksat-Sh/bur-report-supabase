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

app = FastAPI()
# --- config ---
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL environment variable")


# Use asyncpg driver in DATABASE_URL, e.g.:
# postgresql+asyncpg://user:pass@host:port/dbname


engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


Base = declarative_base()
argon2 = PasswordHasher()


SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
ALGORITHM = "HS256"


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")




# --- models ---
class User(Base):
__tablename__ = "users"
id = Column(Integer, primary_key=True)
username = Column(String, unique=True, index=True, nullable=False)
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




# --- helpers ---
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
if not username:
raise HTTPException(status_code=401, detail="Invalid token")
await conn.run_sync(Base.metadata.create_all)
