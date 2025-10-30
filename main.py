import os, io, requests, pandas as pd
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SESSION_KEY = os.getenv("SESSION_KEY", "change-this-secret")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    raise RuntimeError("SUPABASE_URL или SUPABASE_API_KEY не найдены в .env")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_KEY)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

DEFAULT_USERS = {}

def supabase_get(path, params=None):
    return requests.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=SUPABASE_HEADERS, params=params or {})

def supabase_post(path, json_data):
    return requests.post(f"{SUPABASE_URL}/rest/v1/{path}", headers=SUPABASE_HEADERS, json=json_data)

@app.get('/', response_class=HTMLResponse)
def root(request: Request):
    if request.session.get('user'):
        role = request.session['user']['role']
        return RedirectResponse('/dispatcher' if role in ('dispatcher','admin') else '/form')
    return RedirectResponse('/login')

@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse('login.html', {'request': request, 'error': ''})

@app.post('/login')
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    r = supabase_get('users', params={'select':'*', 'username': f'eq.{username}'})
    if r.status_code == 200 and r.json():
        u = r.json()[0]
        if u.get('password_hash') == password:
            request.session['user'] = {'username': u['username'], 'role': u['role'], 'full_name': u.get('full_name'), 'location': u.get('location'), 'rig_number': u.get('rig_number')}
            return RedirectResponse('/', status_code=303)
    # fallback
    return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный логин или пароль'})

@app.get('/form', response_class=HTMLResponse)
def form_page(request: Request):
    user = request.session.get('user')
    if not user or user.get('role') != 'driller':
        return RedirectResponse('/login')
    locations = ['Карамурын','Ирколь','Хорасан','Заречное','Степногорск']
    return templates.TemplateResponse('form.html', {'request': request, 'user': user, 'locations': locations})

@app.post('/submit')
def submit_report(request: Request, meterage: float = Form(...), pogon: float = Form(...), operation: str = Form(''), note: str = Form('')):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401)
    data = {
        'date_time': datetime.now().astimezone().isoformat(),
        'location': user.get('location'),
        'rig_number': user.get('rig_number'),
        'meterage': meterage,
        'pogon': pogon,
        'operation': operation,
        'note': note,
        'operator_name': user.get('full_name'),
        'created_at': datetime.now().astimezone().isoformat()
    }
    r = supabase_post('reports', data)
    if r.status_code not in (200,201):
        raise HTTPException(status_code=500, detail=r.text)
    return {'message':'ok'}

@app.get('/dispatcher', response_class=HTMLResponse)
def dispatcher_page(request: Request):
    user = request.session.get('user')
    if not user or user.get('role') not in ('dispatcher','admin'):
        return RedirectResponse('/login')
    r = supabase_get('reports', params={'select':'*'})
    reports = r.json() if r.status_code==200 else []
    ru = supabase_get('users', params={'select':'id,username,role,full_name,location'})
    users = ru.json() if ru.status_code==200 else []
    return templates.TemplateResponse('dispatcher.html', {'request': request, 'reports': reports, 'users': users, 'user': user})

@app.get('/export_excel')
def export_excel():
    r = supabase_get('reports', params={'select':'*'})
    data = r.json() if r.status_code==200 else []
    if not data:
        raise HTTPException(status_code=404, detail='Нет данных')
    df = pd.DataFrame(data)
    df.rename(columns={'id':'ID','date_time':'Дата и время','location':'Участок','rig_number':'№ агрегата','meterage':'Метраж','pogon':'Погонометр','operation':'Вид операции','note':'Примечание','operator_name':'Ответственное лицо'}, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Сводка')
    output.seek(0)
    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename=svodka.xlsx'})
