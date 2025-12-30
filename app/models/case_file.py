# app/models/case_file.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class CaseFile(Base):
    __tablename__ = "case_files"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)    
    file_size = Column(Integer)
    s3_key = Column(String, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    case = relationship("Case", back_populates="files")
    embeddings = relationship("Embedding", back_populates="file")
    content_type = Column(String, nullable=True)
