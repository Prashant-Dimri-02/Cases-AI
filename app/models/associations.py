# app/models/associations.py
from sqlalchemy import Table, Column, ForeignKey
from app.db.base import Base

# User ↔ Role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE")),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE")),
)
