# app/models/case.py
from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base
from sqlalchemy.orm import relationship

class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, index=True)
    case_name = Column(String(255), nullable=False)
    case_no = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    files = relationship("CaseFile", back_populates="case")
