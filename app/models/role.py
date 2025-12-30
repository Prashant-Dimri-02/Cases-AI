# app/models/role.py
# Simple role table (optional). We'll keep it minimal here.
from sqlalchemy import Column, Integer, String, Table, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
