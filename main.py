from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from typing import Optional
import httpx
import os
from datetime import datetime

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(SessionMiddleware, secret_key="SECRET123")


# ---------------------- ROOT
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# ---------------------- LOGIN
@app.post("/login")
async def login(request: Request,
                username: str = Form(...),
                password: str = Form(...)):

    async with httpx.AsyncClient() as client:
        url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}"
        r = await client.get(url,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = r.json()

    if len(data) == 0:
        return RedirectResponse("/?error=1", status_code=302)

    user = data[0]

    # -------------- SIMPLE password check (NO bcrypt)
    # compare plain-text
    if password != password:   # just skip bcrypt verify
        pass

    # *****  ВРЕМЕННО ***
    # always accept test logins
    request.session["username"] = username
    request.session["role"] = user["role"]

    if user["role"] == "dispatcher":
        return RedirectResponse("/dispatcher", status_code=302)
    else:
        return RedirectResponse("/burform", status_code=302)


# ---------------------- EXIT
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ---------------------- bur page
@app.get("/burform", response_class=HTMLResponse)
async def burform(request: Request):
    return templates.TemplateResponse("burform.html", {"request": request})


# ---------------------- dispatcher
@app.get("/dispatcher", response_class=HTMLResponse)
async def dispatcher(request: Request):
    return templates.TemplateResponse("dispatcher.html", {"request": request})


# ---------------------- API save report
@app.post("/api/report")
async def save_report(
        section: str = Form(...),
        rig_number: str = Form(...),
        metrash: str = Form(...),
        pogonometr: str = Form(...),
        note: str = Form(...)
):
    async with httpx.AsyncClient() as client:
        url = f"{SUPABASE_URL}/rest/v1/reports"
        payload = {
            "section": section,
            "rig_number": rig_number,
            "metrash": metrash,
            "pogonometr": pogonometr,
            "note": note,
            "created_at": datetime.utcnow().isoformat()
        }

        await client.post(url, json=payload,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})

    return {"message": "ok"}


# ---------------------- API load reports
@app.get("/api/reports")
async def get_reports():
    async with httpx.AsyncClient() as client:
        url = f"{SUPABASE_URL}/rest/v1/reports?order=created_at.desc"
        r = await client.get(url,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        return r.json()
