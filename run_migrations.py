cat > run_migrations.py <<'PY'
# run_migrations.py
import os
from sqlalchemy import create_engine, text
from database import DATABASE_URL

print("Running migrations...")
engine = create_engine(DATABASE_URL, future=True)
with engine.connect() as conn:
    statements = [
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS mbu VARCHAR;",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS responsible VARCHAR;"
    ]
    for s in statements:
        try:
            conn.execute(text(s))
            print("Executed:", s)
        except Exception as e:
            print("Error executing:", s, e)
print("Done.")
PY
