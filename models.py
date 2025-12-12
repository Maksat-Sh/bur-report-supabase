from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_dispatcher = Column(Boolean, default=False)

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    site = Column(String(100))
    rig_number = Column(String(50))
    metraj = Column(Float, default=0.0)
    pogonometr = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)
