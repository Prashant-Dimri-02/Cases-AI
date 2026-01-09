# app/models/case.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_name = Column(String(255), nullable=False)
    case_no = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # ✅ RENAMED (important!)
    case_metadata = relationship(
    "CaseMetadata",
    uselist=False,
    back_populates="case",
    cascade="all, delete",
    passive_deletes=True,
    lazy="selectin",
)

    files = relationship(
        "CaseFile",
        back_populates="case",
        cascade="all, delete",
        passive_deletes=True,
        order_by="CaseFile.created_at.desc()",
        lazy="selectin",
    )

    sessions = relationship(
        "ChatSession",
        back_populates="case",
        cascade="all, delete",
        passive_deletes=True,
    )
