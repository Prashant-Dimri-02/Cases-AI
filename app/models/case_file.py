# app/models/case_file.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Enum, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class FileStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    REJECTED = "REJECTED"


class CaseFile(Base):
    __tablename__ = "case_files"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    file_size = Column(Integer)
    content_type = Column(String, nullable=True)

    status = Column(
        Enum(FileStatus, name="file_status_enum"),
        default=FileStatus.DRAFT,
        nullable=False,
        index=True
    )

    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    requested_at = Column(DateTime, nullable=True)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    processed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # relationships
    case = relationship("Case", back_populates="files", lazy="selectin")

    embeddings = relationship(
        "Embedding",
        back_populates="file",
        cascade="all, delete",
        passive_deletes=True
    )

    requested_user = relationship(
        "User",
        foreign_keys=[requested_by],
        lazy="select"
    )

    approved_user = relationship(
        "User",
        foreign_keys=[approved_by],
        lazy="select"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','PENDING','APPROVED','PROCESSING','PROCESSED','REJECTED')",
            name="check_file_status"
        ),
    )