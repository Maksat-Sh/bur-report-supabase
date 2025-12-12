import os, urllib.parse
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from database import engine, AsyncSessionLocal
from models import Base, User, Report
from schemas import ReportCreate
from auth import hash_password, verify_password, create_access_token
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import asyncio

templates = Jinja2Templates(directory='templates')
app = FastAPI()

# Create DB tables on startup
async def init_models():
    # create tables (sync engine via greenlet spawn is handled by SQLAlchemy)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def on_start():
    await init_models()
    # create a default dispatcher user if not exists
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == 'dispatcher'))
        user = result.scalar_one_or_none()
        if not user:
            u = User(username='dispatcher', hashed_password=hash_password('1234'), is_dispatcher=True)
            db.add(u)
            await db.commit()

# Dependency
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})

@app.post("/token")
async def login(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    # authenticate
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": user.username})
    # simple redirect to dispatcher page (in real app, you'd return token JSON)
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("access_token", token)
    return resp

@app.post("/reports")
async def create_report(report: ReportCreate, db: AsyncSession = Depends(get_db)):
    r = Report(
        site=report.site,
        rig_number=report.rig_number,
        metraj=report.metraj or 0.0,
        pogonometr=report.pogonometr,
        note=report.note,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"message": "Report submitted successfully", "id": r.id}
