# bur-report-supabase (prepared)

Файлы:
- main.py — FastAPI приложение
- templates/* — html-шаблоны
- static/style.css — стили
- requirements.txt — зависимости

Перед деплоем в Render укажи переменные окружения:
- SUPABASE_URL = https://...supabase.co
- SUPABASE_SERVICE_ROLE_KEY (или SUPABASE_ANON_KEY)
- SESSION_KEY = любой_секретный_ключ

Если Supabase не настроен — приложение всё ещё работает в "локальном" режиме (локальные пользователи).
