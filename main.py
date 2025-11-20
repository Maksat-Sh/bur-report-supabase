from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import datetime
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://report_oag9_user:ptL2Iv17CqIkUJWLWmYmeVMqJhOVhXi7@dpg-d28s8r433s73btijog-a/report_oag9")

app = FastAPI()

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_db():
    return await asyncpg.connect(DATABASE_URL)


# ================================================================
#   UTILS
# ================================================================

async def get_user_by_username(username: str):
    conn = await get_db()
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE username=$1", username
    )
    await conn.close()
    return row


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def hash_password(password: str):
    return pwd_context.hash(password)

@app.get("/create_user_form", response_class=HTMLResponse)
async def create_user_form(request: Request):
    return templates.TemplateResponse(
        "create_user_form.html",
        {"request": request}
    )

# ================================================================
#   AUTH LOGIN
# ================================================================

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await get_user_by_username(form_data.username)

    if not user:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")

    if not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")

    return {
        "access_token": user["username"],
        "role": user["role"],
        "token_type": "bearer"
    }


# ================================================================
#   CREATE USER (временно включено)
# ================================================================

@app.post("/create_user")
async def create_user(username: str, password: str, full_name: str, role: str = "driller"):
    conn = await get_db()

    hashed = hash_password(password)

    try:
        await conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            username, hashed, full_name, role, datetime.utcnow()
        )
    except Exception as e:
        return {"error": str(e)}

    await conn.close()

    return {"status": "ok", "username": username}


# ================================================================
#   SUBMIT REPORT (буровик)
# ================================================================

@app.post("/submit_report")
async def submit_report(
    username: str = Form(...),
    section: str = Form(...),
    rig_number: str = Form(...),
    meterage: str = Form(...),
    pogon: str = Form(...),
    operation: str = Form(...),
    responsible: str = Form(...),
    note: str = Form("")
):
    conn = await get_db()

    await conn.execute(
        """
        INSERT INTO reports (username, section, rig_number, meterage, pogon, operation, responsible, note, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        username, section, rig_number, meterage, pogon,
        operation, responsible, note, datetime.utcnow()
    )

    await conn.close()

    return {"message": "Report submitted successfully"}


# ================================================================
#   GET REPORTS (диспетчер)
# ================================================================

@app.get("/get_reports")
async def get_reports(token: str = Depends(oauth2_scheme)):
    user = await get_user_by_username(token)
    if not user or user["role"] != "dispatcher":
        raise HTTPException(status_code=403, detail="Access denied")

    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at DESC")
    await conn.close()

    return rows


# ================================================================
#   ROOT — /dispatcher.html
# ================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("dispatcher.html", encoding="utf-8") as f:
        return f.read()
