from fastapi import FastAPI, Request, Form
user = get_current_user(request)
if not user or user.get('role') != 'dispatcher':
return RedirectResponse('/login')
params = '?select=*&order=created_at.desc'
if section:
params = f'?select=*&order=created_at.desc&section=eq.{section}'
reports = await supabase_get('reports', params=params)
sites = ['','Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
return templates.TemplateResponse('dispatcher.html', {'request': request, 'user': user, 'reports': reports, 'sites': sites, 'selected_site': section or ''})


# Export Excel
@app.get('/export_excel')
async def export_excel(request: Request, section: str | None = None):
user = get_current_user(request)
if not user or user.get('role') != 'dispatcher':
return RedirectResponse('/login')
params = '?select=*&order=created_at.desc'
if section:
params = f'?select=*&order=created_at.desc&section=eq.{section}'
reports = await supabase_get('reports', params=params)
wb = Workbook()
ws = wb.active
ws.title = 'reports'
ws.append(['ID','Дата UTC','Участок','Номер агрегата','Метраж','Погонометр','Операция','Автор','Примечание'])
for r in reports:
created = r.get('created_at') or r.get('timestamp') or ''
ws.append([r.get('id'), created, r.get('section') or r.get('location'), r.get('rig_number'), r.get('meterage'), r.get('pogonometr'), r.get('operation_type') or r.get('operation'), r.get('operator_name'), r.get('note') or ''])
stream = io.BytesIO()
wb.save(stream)
stream.seek(0)
filename = f"reports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
return StreamingResponse(stream, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers)


# Users page (dispatcher only)
@app.get('/users', response_class=HTMLResponse)
async def users_page(request: Request):
user = get_current_user(request)
if not user or user.get('role') != 'dispatcher':
return RedirectResponse('/login')
users = await supabase_get('users', params='?select=*')
sites = ['Хорасан','Заречное','Карамурын','Ирколь','Степногорск']
return templates.TemplateResponse('users.html', {'request': request, 'user': user, 'users': users, 'sites': sites})


# Create user (dispatcher)
@app.post('/create_user')
async def create_user(request: Request, username: str = Form(...), full_name: str = Form(''), password: str = Form(...), role: str = Form(...), location: str | None = Form(None)):
admin = get_current_user(request)
if not admin or admin.get('role') != 'dispatcher':
return RedirectResponse('/login')
payload = {
'username': username,
'full_name': full_name,
'fio': full_name,
'password': password,
'password_hash': hashlib.sha256(password.encode()).hexdigest(),
'role': role,
'location': location,
'created_at': datetime.utcnow().isoformat()
}
await supabase_post('users', payload)
return RedirectResponse('/users', status_code=303)


# Ping
@app.get('/ping')
def ping():
return {'status':'ok'}
