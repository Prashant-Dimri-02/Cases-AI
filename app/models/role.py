# app/models/role.py
from sqlalchemy import Column, Integer, String, Table, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship
from app.models.associations import user_roles

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    users = relationship(
    "User",
    secondary=user_roles,
    back_populates="roles"
)