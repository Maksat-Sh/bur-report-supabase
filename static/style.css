cat > static/style.css <<'CSS'
body{font-family: Arial, sans-serif; padding:20px}
.topbar{display:flex; gap:10px; justify-content:flex-end; margin-bottom:20px}
.topbar .btn{background:#0b5ed7;color:#fff;padding:8px 12px;border-radius:8px;text-decoration:none}
CSS

cat > static/app.js <<'JS'
// Simple fetch to show reports on dispatcher page
async function loadReports(){
  try{
    const res = await fetch('/api/reports');
    if(!res.ok){ throw new Error('network'); }
    const data = await res.json();
    const el = document.getElementById('reports');
    if(!data || data.length===0){ el.innerHTML = '<p>Нет записей</p>'; return; }
    let html = '<table border="1" width="100%"><tr><th>ID</th><th>Дата/время</th><th>Участок</th><th>Буровая</th><th>Метраж</th><th>Погонометр</th><th>Примечание</th></tr>';
    for(const r of data){
      html += `<tr><td>${r.id}</td><td>${r.datetime}</td><td>${r.site}</td><td>${r.rig}</td><td>${r.metr}</td><td>${r.pogonomet}</td><td>${r.note||''}</td></tr>`;
    }
    html += '</table>';
    el.innerHTML = html;
  }catch(e){
    document.getElementById('reports').innerHTML = '<div style="color:red">Ошибка загрузки</div>';
  }
}
if(document.getElementById('reports')) loadReports();
JS
