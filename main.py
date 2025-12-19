import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, text, select
from passlib.context import CryptContext

# ------------------ НАСТРОЙКИ ------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@host/dbname?ssl=require"
)

DISPATCHER_LOGIN = os.getenv("DISPATCHER_LOGIN", "dispatcher")
DISPATCHER_PASSWORD = os.getenv("DISPATCHER_PASSWORD", "1234")

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ------------------ APP ------------------

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# ------------------ DB ------------------

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)


# ------------------ UTILS ------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hash_: str) -> bool:
    return pwd_context.verify(password, hash_)


def require_dispatcher(request: Request):
    if not request.session.get("dispatcher"):
        raise HTTPException(status_code=401)
    return True


# ------------------ ROUTES ------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("dispatcher"):
        return RedirectResponse("/dispatcher", 302)
    return RedirectResponse("/login", 302)


# ---------- LOGIN ----------

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <h2>Вход диспетчера</h2>
    <form method="post">
        <input name="login" placeholder="Логин"><br>
        <input name="password" type="password" placeholder="Пароль"><br>
        <button>Войти</button>
    </form>
    """


@app.post("/login")
async def login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...)
):
    if login == DISPATCHER_LOGIN and password == DISPATCHER_PASSWORD:
        request.session["dispatcher"] = True
        return RedirectResponse("/dispatcher", 302)

    return HTMLResponse("<h3>Неверный логин или пароль</h3>", status_code=401)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)


# ---------- DISPATCHER ----------

@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher_page(request: Request, _=Depends(require_dispatcher)):
    return """
    <h2>Панель диспетчера</h2>

    <h3>Создать пользователя буровика</h3>
    <form method="post" action="/dispatcher/create-user">
        <input name="username" placeholder="Логин"><br>
        <input name="password" placeholder="Пароль"><br>
        <button>Создать</button>
    </form>

    <br>
    <a href="/logout">Выйти</a>
    """


@app.post("/dispatcher/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    _=Depends(require_dispatcher)
):
    async with AsyncSessionLocal() as db:
        exists = await db.scalar(select(User).where(User.username == username))
        if exists:
            return HTMLResponse("❌ Пользователь уже существует", 400)

        user = User(
            username=username,
            password_hash=hash_password(password)
        )
        db.add(user)
        await db.commit()

    return RedirectResponse("/dispatcher", 302)


# ---------- DB CHECK ----------

@app.get("/db-check")
async def db_check():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"db": "ok"}


# ---------- INIT TABLES (РУЧНО) ----------

@app.get("/init-db")
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return {"status": "tables created"}
