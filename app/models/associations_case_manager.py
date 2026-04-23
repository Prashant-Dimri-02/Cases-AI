# app/models/associations_case_manager.py

from sqlalchemy import Table, Column, Integer, ForeignKey
from app.db.base import Base

case_managers = Table(
    "case_managers",
    Base.metadata,
    Column("case_id", Integer, ForeignKey("cases.id")),
    Column("user_id", Integer, ForeignKey("users.id"))
)