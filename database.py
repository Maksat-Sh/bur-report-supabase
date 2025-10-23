# database.py - improved connection & check
import os, time, logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.warning("DATABASE_URL not set — falling back to SQLite (bur_reports.db).")
    DATABASE_URL = "sqlite:///./bur_reports.db"

# ensure correct driver prefix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

connect_args = {}
if DATABASE_URL.startswith("postgresql+psycopg2://") or "postgresql://" in DATABASE_URL:
    if "sslmode" not in DATABASE_URL:
        if "?" in DATABASE_URL:
            DATABASE_URL = DATABASE_URL + "&sslmode=require"
        else:
            DATABASE_URL = DATABASE_URL + "?sslmode=require"
    connect_args = {"sslmode": "require"}

engine = None
max_retries = 5
for attempt in range(1, max_retries + 1):
    try:
        logger.info(f"Creating engine (attempt {attempt}/{max_retries})...")
        engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, connect_args=connect_args, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Connected successfully to PostgreSQL")
        break
    except Exception as e:
        logger.warning(f"Database connect attempt {attempt} failed: {e}")
        if attempt < max_retries:
            time.sleep(2 ** attempt)
        else:
            logger.error("All database connection attempts failed. Falling back to SQLite.")
            DATABASE_URL = "sqlite:///./bur_reports.db"
            engine = create_engine(DATABASE_URL, future=True)
            break

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

