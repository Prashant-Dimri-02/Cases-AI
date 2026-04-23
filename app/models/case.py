# app/models/case.py
from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.associations_case_user import case_users
from app.db.base import Base
from app.models.associations_case_manager import case_managers


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_name = Column(String(255), nullable=False)
    case_no = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    managers = relationship(
        "User",
        secondary=case_managers,
        backref="managed_cases"
    )
    users = relationship("User", secondary=case_users, backref="cases")

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

    upcoming_meetings = relationship(
        "UpcomingMeeting",
        back_populates="case",
        cascade="all, delete-orphan",
    )