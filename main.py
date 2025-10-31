import os
import io
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
import requests
import pandas as pd

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ovkfakpwgvrpbnjbrkza.supabase.co')
SUPABASE_API_KEY = os.environ.get('SUPABASE_API_KEY', 'SET_YOUR_KEY_HERE')
SESSION_KEY = os.environ.get('SESSION_KEY', '123456789abcdef')

app = FastAPI()
templates = Jinja2Templates(directory='templates')
app.mount('/static', StaticFiles(directory='static'), name='static')

def sb_headers():
    return {
        'apikey': SUPABASE_API_KEY,
        'Authorization': f'Bearer {SUPABASE_API_KEY}',
        'Content-Type': 'application/json'
    }

@app.get('/', response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse('/form')

@app.get('/form', response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse('form.html', {'request': request})

@app.post('/submit')
async def submit_report(request: Request,
                        date_time: str = Form(None),
                        site: str = Form(...),
                        unit_number: str = Form(...),
                        metraj: str = Form(''),
                        pogonometr: str = Form(''),
                        operation: str = Form(''),
                        responsible: str = Form(''),
                        notes: str = Form('')):
    payload = {
        'date_time': date_time or None,
        'site': site,
        'unit_number': unit_number,
        'metraj': metraj,
        'pogonometr': pogonometr,
        'operation': operation,
        'responsible': responsible,
        'notes': notes
    }
    url = f"{SUPABASE_URL}/rest/v1/reports"
    resp = requests.post(url, headers=sb_headers(), data=json.dumps(payload))
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=resp.text)
    return {'message': 'Report submitted successfully', 'response': resp.json()}

@app.get('/login', response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {'request': request})

@app.post('/login')
async def login_post(username: str = Form(...), password: str = Form(...)):
    if username == 'admin' and password == '1234':
        resp = RedirectResponse(url='/dispatcher', status_code=303)
        resp.set_cookie('session', 'admin-session', httponly=True)
        return resp
    return templates.TemplateResponse('login.html', {'request': request, 'error': 'Invalid credentials'})

def require_admin(request: Request):
    session = request.cookies.get('session')
    if session != 'admin-session':
        raise HTTPException(status_code=401, detail='Unauthorized')

@app.get('/dispatcher', response_class=HTMLResponse)
async def dispatcher_page(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse('/login')
    return templates.TemplateResponse('dispatcher.html', {'request': request, 'user': {'full_name':'Диспетчер общий'}})

@app.get('/export_excel')
async def export_excel(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail='Unauthorized')
    url = f"{SUPABASE_URL}/rest/v1/reports?select=*"
    resp = requests.get(url, headers=sb_headers())
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=resp.text)
    data = resp.json()
    if not isinstance(data, list):
        data = [data]
    if len(data) == 0:
        import pandas as pd
        df = pd.DataFrame(columns=['date_time','site','unit_number','metraj','pogonometr','operation','responsible','notes'])
    else:
        df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='reports')
    output.seek(0)
    headers = {'Content-Disposition': 'attachment; filename="reports.xlsx"'}
    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers)
