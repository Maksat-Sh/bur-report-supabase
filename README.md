Установи зависимости
python -m pip install -r requirements.txt


2) Задай переменные окружения
export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname"
export SECRET_KEY="..."


3) Запусти
uvicorn main:app --host 0.0.0.0 --port 8000


* На старте приложение автоматически создаст таблицы, если их нет.
