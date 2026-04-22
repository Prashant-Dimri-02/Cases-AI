# app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship
from app.models.associations import user_roles
from datetime import datetime
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(String, default=func.now())

    refresh_tokens = relationship("RefreshToken", back_populates="user")

    roles = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users"
    )

    # ✅ FIX: reverse mappings
    owned_cases = relationship(
        "Case",
        foreign_keys="Case.owner_id",
        back_populates="owner"
    )
