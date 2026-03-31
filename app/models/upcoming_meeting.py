# app/models/upcoming_meeting.py

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class UpcomingMeeting(Base):
    __tablename__ = "upcoming_meetings"

    id = Column(Integer, primary_key=True)
    
    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Microsoft Graph metadata
    graph_event_id = Column(String(255), nullable=False, unique=True, index=True)

    # Meeting info
    subject = Column(String(255), nullable=False)
    meeting_body = Column(Text, nullable=True)

    # 🔑 Bot uses this to join
    join_url = Column(Text, nullable=False)
    
    meeting_title = Column(String(255), nullable=True)

    # Timing (always store UTC)
    start_time_utc = Column(DateTime, nullable=False, index=True)
    end_time_utc = Column(DateTime, nullable=False)
    timezone = Column(String(64), nullable=False)

    # Participants (emails)
    participants = Column(JSON, nullable=False)

    # Bot control flags
    bot_should_join = Column(Boolean, default=True)
    bot_joined = Column(Boolean, default=False)
    bot_joined_at = Column(DateTime, nullable=True)
    bot_left_at = Column(DateTime, nullable=True)

    # Lifecycle status
    status = Column(String(32), default="scheduled", index=True)
    # scheduled | live | completed | cancelled | failed

    # Audit
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    case = relationship("Case", back_populates="upcoming_meetings")