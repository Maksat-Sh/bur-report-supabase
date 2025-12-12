# bur_report - minimal async FastAPI project

This is a minimal, ready-to-deploy FastAPI project tailored for the reports app you described.
It uses SQLAlchemy (async) + asyncpg for PostgreSQL and falls back to SQLite if DATABASE_URL is not provided.

## Files
- `main.py` — FastAPI app, routes (login, token, report submit, dispatcher page).
- `database.py` — Engine and session maker with handling of `sslmode=require` query param.
- `models.py` — ORM models (User, Report).
- `schemas.py` — Pydantic schemas for requests/responses.
- `auth.py` — simple password hashing and token creation (JWT).
- `templates/` — HTML templates for login and dispatcher.
- `static/` — CSS.
- `requirements.txt` — Python dependencies.

## Important notes about PostgreSQL / Render
Render gives you a DATABASE_URL like:

`postgresql://user:pass@host/dbname` or `postgresql+asyncpg://...`

If you get errors about `sslmode` or `SSL/TLS required`, use one of these approaches:

1. **Preferred**: Set `DATABASE_URL` exactly as Render provides (`postgresql://...`) and the code will detect `sslmode=require` in the query part and convert it to a proper `connect_args={"ssl": True}` for asyncpg.
2. **Alternative**: Remove `?sslmode=require` from the URL and instead set an environment variable `DB_SSL=true`; the app will enable SSL accordingly.

## How to run locally
1. Create a virtualenv and install requirements:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Export DATABASE_URL (optional). If absent the app uses SQLite at `./data/test.db`.
3. Run:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Deploy on Render
- Set `DATABASE_URL` in Render's environment variables (the full url Render shows).
- If your URL includes `?sslmode=require`, it's OK — the app handles that by converting to asyncpg connect args.

If you want, I can now:
- Add more pages (Excel export, full dispatcher UI)
- Adjust DB schema to match exact columns you want (погонометр, керн, агрегаты и т.д.)

