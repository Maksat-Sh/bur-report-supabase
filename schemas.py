from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReportCreate(BaseModel):
    site: Optional[str] = None
    rig_number: Optional[str] = None
    metraj: Optional[float] = 0.0
    pogonometr: Optional[str] = None
    note: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'
