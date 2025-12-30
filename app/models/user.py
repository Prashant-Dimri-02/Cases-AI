# app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(String, default=func.now())
    refresh_tokens = relationship("RefreshToken", back_populates="user")
