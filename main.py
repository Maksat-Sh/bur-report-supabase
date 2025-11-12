from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import io
from openpyxl import Workbook
import hashlib
from passlib.context import CryptContext

# Load env
load_dotenv()
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')
SECRET_KEY = os.getenv('SECRET_KEY','dev-secret')
TZ_OFFSET = int(os.getenv('TIMEZONE_OFFSET_HOURS','5'))  # Kazakhstan UTC+5

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError('Please set SUPABASE_URL and SUPABASE_ANON_KEY in environment (.env)')

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory='templates')
app.mount('/static', StaticFiles(directory='static'), name='static')

# Supabase REST helpers (PostgREST)
headers = {'apikey': SUPABASE_ANON_KEY, 'Authorization': f'Bearer {SUPABASE_ANON_KEY}', 'Content-Type': 'application/json'}
# Настройка шифрования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Поддержка bcrypt и sha256"""
    try:
        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            return pwd_context.verify(plain_password, hashed_password)
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    except Exception:
        return False

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def get_now():
    # return timezone-aware UTC then shift to timezone offset for display purposes
    u = datetime.utcnow().replace(tzinfo=timezone.utc)
    return (u + timedelta(hours=TZ_OFFSET)).replace(tzinfo=None)

def get_current_user(request: Request):
    return request.session.get('user')

@app.get('/', response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse('/login')

@app.get('/login', response_class=HTMLResponse)
def login_get(request: Request, error: str | None = None):
    return templates.TemplateResponse('login.html', {'request': request, 'error': error})

@app.post('/login', response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Authenticate via users table on Supabase
    async with httpx.AsyncClient() as client:
        # Use filter username eq.
        r = await client.get(f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}&select=*", headers=headers)
        if r.status_code != 200 or not r.json():
            return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный логин или пароль'})
        user = r.json()[0]
        # Support storing plain 'password' or hashed 'password_hash' for backwards compatibility
        pw_hash = user.get('password_hash') or (hashlib.sha256(user.get('password','').encode()).hexdigest() if user.get('password') else None)
        if not verify_password(password, pw_hash):
            return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный логин или пароль'})
        # store essential info
        request.session['user'] = {'username': user.get('username'), 'full_name': user.get('full_name') or user.get('fio') or user.get('username'), 'role': user.get('role') or 'worker', 'site': user.get('location') or user.get('site')}
        if request.session['user']['role'] == 'dispatcher':
            return RedirectResponse('/dispatcher', status_code=303)
        return RedirectResponse('/worker_form', status_code=303)

@app.get('/logout')
def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse('/login')

@app.get('/worker_form', response_class=HTMLResponse)
def worker_form(request: Request):
    user = get_current_user(request)
    if not user or user.get('role') != 'worker':
        return RedirectResponse('/login')
    # Sites hardcoded as requested
    sites = ['Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
    now = get_now().strftime('%Y-%m-%d %H:%M:%S')
    return templates.TemplateResponse('worker_form.html', {'request': request, 'user': user, 'sites': sites, 'now': now, 'success': None})

@app.post('/submit_worker_report', response_class=HTMLResponse)
async def submit_worker_report(request: Request,
                               site: str = Form(...),
                               rig_number: str = Form(...),
                               meterage: float = Form(...),
                               pogonometr: float = Form(...),
                               operation: str = Form(...),
                               note: str = Form('')):
    user = get_current_user(request)
    if not user or user.get('role') != 'worker':
        return RedirectResponse('/login')
    payload = {
        'section': site,
        'rig_number': rig_number,
        'meterage': meterage,
        'pogonometr': pogonometr,
        'operation_type': operation,
        'note': note,
        # store operator_name as username for stable mapping; full name kept in fio column optionally
        'operator_name': user.get('username'),
        'created_at': datetime.utcnow().isoformat()  # server side timestamp in UTC
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/reports", headers=headers, json=payload)
        if r.status_code in (201, 200):
            sites = ['Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
            now = get_now().strftime('%Y-%m-%d %H:%M:%S')
            return templates.TemplateResponse('worker_form.html', {'request': request, 'user': user, 'sites': sites, 'now': now, 'success': 'Отчёт сохранён'})
        else:
            return templates.TemplateResponse('worker_form.html', {'request': request, 'user': user, 'sites': sites, 'now': get_now().strftime('%Y-%m-%d %H:%M:%S'), 'success': f'Ошибка при сохранении: {r.text}'})

@app.get('/dispatcher', response_class=HTMLResponse)
async def dispatcher_view(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get('role') != 'dispatcher':
        return RedirectResponse('/login')
    params = 'select=*&order=created_at.desc'
    if section:
        params = 'select=*&order=created_at.desc&section=eq.' + section
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/reports?{params}", headers=headers)
        reports = r.json() if r.status_code == 200 else []
    sites = ['','Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
    return templates.TemplateResponse('dispatcher.html', {'request': request, 'user': user, 'reports': reports, 'sites': sites, 'selected_site': section or ''})

@app.get('/export_excel')
async def export_excel(request: Request, section: str | None = None):
    user = get_current_user(request)
    if not user or user.get('role') != 'dispatcher':
        return RedirectResponse('/login')
    params = 'select=*&order=created_at.desc'
    if section:
        params = 'select=*&order=created_at.desc&section=eq.' + section
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/reports?{params}", headers=headers)
        reports = r.json() if r.status_code == 200 else []
    wb = Workbook()
    ws = wb.active
    ws.title = 'reports'
    ws.append(['ID','Дата UTC','Участок','Номер агрегата','Метраж','Погонометр','Операция','Автор','Примечание'])
    for r in reports:
        created = r.get('created_at') or r.get('timestamp') or ''
        ws.append([r.get('id'), created, r.get('section'), r.get('rig_number'), r.get('meterage'), r.get('pogonometr'), r.get('operation_type'), r.get('operator_name'), r.get('note') or ''])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers_out = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(stream, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers_out)

@app.get('/users', response_class=HTMLResponse)
async def users_page(request: Request):
    user = get_current_user(request)
    if not user or user.get('role') != 'dispatcher':
        return RedirectResponse('/login')
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/users?select=*") 
        all_users = r.json() if r.status_code == 200 else []
    sites = ['Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
    return templates.TemplateResponse('users.html', {'request': request, 'user': user, 'users': all_users, 'sites': sites, 'error': None})

@app.post('/create_user')
async def create_user(request: Request, username: str = Form(...), full_name: str = Form(''), password: str = Form(...), role: str = Form(...), site: str | None = Form(None)):
    admin = get_current_user(request)
    if not admin or admin.get('role') != 'dispatcher':
        return RedirectResponse('/login')
    payload = {
        'username': username,
        'full_name': full_name,
        'password_hash': hashlib.sha256(password.encode()).hexdigest(),
        'password': password,  # optional plain (legacy)
        'fio': full_name,
        'role': role,
        'location': site,
        'created_at': datetime.utcnow().isoformat()
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/users", headers=headers, json=payload)
        if r.status_code in (201, 200):
            return RedirectResponse('/users', status_code=303)
        else:
            # show error on page
            async with httpx.AsyncClient() as client2:
                ru = await client2.get(f"{SUPABASE_URL}/rest/v1/users?select=*")
                all_users = ru.json() if ru.status_code==200 else []
            sites = ['Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
            return templates.TemplateResponse('users.html', {'request': request, 'user': admin, 'users': all_users, 'sites': sites, 'error': r.text})
