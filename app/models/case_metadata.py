# app/models/case_metadata.py
from sqlalchemy import Column, Integer, Text, Date, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

class CaseMetadata(Base):
    __tablename__ = "case_metadata"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), unique=True, nullable=False)

    parties = Column(JSONB, nullable=True)
    court_name = Column(Text, nullable=True)
    filing_date = Column(Date, nullable=True)
    judge = Column(Text, nullable=True)
    attorney = Column(Text, nullable=True)
    next_court_date = Column(Date, nullable=True)
    strong_evidence = Column(Text, nullable=True)
    approaching_deadline = Column(Boolean, nullable=True)
    case_description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now())
    updated_at = Column(DateTime(timezone=False), onupdate=func.now())
    case = relationship(
        "Case",
        back_populates="case_metadata",
    )