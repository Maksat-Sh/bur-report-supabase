import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
import urllib.parse

DATABASE_URL = os.environ.get("DATABASE_URL")
# fallback to sqlite
if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///./data/test.db"

# handle sslmode in query for asyncpg (asyncpg expects ssl parameter, not sslmode)
def create_engine_from_url(url: str) -> AsyncEngine:
    # parse URL
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    connect_args = {}
    clean_url = url
    # If sslmode present and true-ish -> set connect_args['ssl']=True and remove from URL
    if 'sslmode' in qs:
        sslv = qs.get('sslmode', [''])[0]
        if sslv and sslv != 'disable':
            connect_args['ssl'] = True
        # remove sslmode from query and rebuild URL
        qdict = {k:v for k,v in qs.items() if k != 'sslmode'}
        new_q = urllib.parse.urlencode({k:v[0] for k,v in qdict.items()})
        cleaned = parsed._replace(query=new_q)
        clean_url = urllib.parse.urlunparse(cleaned)

    # For SQLAlchemy asyncpg we might want the async driver scheme; the user can set it.
    engine = create_async_engine(
        clean_url,
        echo=False,
        future=True,
        connect_args=connect_args or None,
    )
    return engine

engine = create_engine_from_url(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
