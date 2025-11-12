        # Bur Report — FastAPI + Supabase REST scaffold

This project is a ready-to-edit scaffold for a small FastAPI app that uses **Supabase REST API** (PostgREST) as the backend.

## What is included
- `main.py` — FastAPI app using Supabase REST API via `httpx`.
- `templates/` — Jinja2 HTML templates (login, worker form, dispatcher, users).
- `static/style.css` — minimal CSS.
- `requirements.txt` — Python deps.
- `.env.example` — example environment variables with Supabase URL and ANON KEY.

## Setup
1. Copy `.env.example` -> `.env` and fill SUPABASE_URL and SUPABASE_ANON_KEY.
2. Create a virtualenv and install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Notes
- This scaffold uses the Supabase (PostgREST) endpoints to perform CRUD.
- Adjust table/column names if your schema differs. The README inside `main.py` describes mapping.
