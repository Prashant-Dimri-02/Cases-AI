# app/models/associations_case_user.py
from sqlalchemy import Table, Column, ForeignKey
from app.db.base import Base

case_users = Table(
    "case_users",
    Base.metadata,
    Column("case_id", ForeignKey("cases.id", ondelete="CASCADE")),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE")),
)