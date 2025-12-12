import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt

PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET = os.environ.get('SECRET_KEY', 'dev-secret-key')

def hash_password(password: str) -> str:
    return PWD_CTX.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return PWD_CTX.verify(plain, hashed)

def create_access_token(data: dict, expires_minutes: int = 60):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET, algorithm="HS256")
