# app/models/chat_message.py
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Text, nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    meta = Column(Text, nullable=True)  # optional: store json string if needed for attachments/metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationship back to session
    session = relationship("ChatSession", back_populates="messages")
