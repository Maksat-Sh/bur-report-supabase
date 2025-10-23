# supabase_client.py
import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")  # https://<project>.supabase.co
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # anon or service key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment")

BASE_REST = SUPABASE_URL.rstrip("/") + "/rest/v1"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def insert_report(payload: dict):
    """Insert report into reports table via PostgREST"""
    url = f"{BASE_REST}/reports"
    r = requests.post(url, json=payload, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def select_reports(params: dict = None):
    """Get reports. params -> query string dict"""
    url = f"{BASE_REST}/reports"
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def insert_user(payload: dict):
    url = f"{BASE_REST}/users"
    r = requests.post(url, json=payload, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_users():
    url = f"{BASE_REST}/users"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_user_by_username(username):
    url = f"{BASE_REST}/users"
    # filter username=eq.<username>
    r = requests.get(url, headers=HEADERS, params={"username": f"eq.{username}"})
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None
