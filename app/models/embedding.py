# app/models/embedding.py
from sqlalchemy import Column, Integer, ForeignKey, Float, ARRAY, Text
from sqlalchemy.orm import relationship
from app.db.base import Base

class Embedding(Base):
    __tablename__ = "embeddings"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    # store vector as postgres float[]; change to pgvector.Vector if you add the pgvector package
    vector = Column(ARRAY(Float), nullable=False)
    document_metadata = Column(Text, nullable=True)
    file = relationship("CaseFile", back_populates="embeddings")
