import os
@app.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_page(request: Request):
user = request.session.get("user")
if not user or user.get("role") not in ("dispatcher", "admin"):
return RedirectResponse("/login")


reports_list = []
if USE_SUPABASE:
r = supabase_get_reports()
if r.status_code == 200:
reports_list = r.json()
else:
with engine.connect() as conn:
rows = conn.execute(select(reports).order_by(reports.c.created_at.desc())).fetchall()
for row in rows:
reports_list.append({
"id": row.id,
"date_time": row.date_time.isoformat() if row.date_time else None,
"location": row.location,
"rig_number": row.rig_number,
"meterage": row.meterage,
"pogon": row.pogon,
"note": row.note,
"operator_name": row.operator_name,
"created_at": row.created_at.isoformat() if row.created_at else None
})


return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "reports": reports_list})


# --- Export to Excel ---
@app.get("/export_excel")
def export_excel():
# fetch data
data = []
if USE_SUPABASE:
r = supabase_get_reports()
if r.status_code == 200:
data = r.json()
else:
raise HTTPException(500, f"Ошибка при получении данных из Supabase: {r.status_code}")
else:
with engine.connect() as conn:
rows = conn.execute(select(reports).order_by(reports.c.created_at.desc())).fetchall()
for row in rows:
data.append({
"id": row.id,
"date_time": row.date_time.isoformat() if row.date_time else None,
"location": row.location,
"rig_number": row.rig_number,
"meterage": row.meterage,
"pogon": row.pogon,
"note": row.note,
"operator_name": row.operator_name,
"created_at": row.created_at.isoformat() if row.created_at else None
})


if not data:
return {"error": "Нет данных для экспорта"}


df = pd.DataFrame(data)
# ensure columns exist
expected = ["id", "date_time", "location", "rig_number", "meterage", "pogon", "note", "operator_name", "created_at"]
for c in expected:
if c not in df.columns:
df[c] = None

