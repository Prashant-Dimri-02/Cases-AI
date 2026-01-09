# app/services/chat_service.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List

from app import models
from app.services.qa_service import QAService


class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def open_session(self, case_id: int):
        # 1️⃣ Find existing open session
        session = (
            self.db.query(models.ChatSession)
            .filter(
                models.ChatSession.case_id == case_id,
                models.ChatSession.closed == False
            )
            .order_by(models.ChatSession.created_at.desc())
            .first()
        )

        # 2️⃣ If none exists, create new
        if not session:
            session = models.ChatSession(case_id=case_id)
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)

        # 3️⃣ Fetch ALL messages for UI (ordered)
        messages = (
            self.db.query(models.ChatMessage)
            .filter(models.ChatMessage.session_id == session.id)
            .order_by(models.ChatMessage.created_at.asc())
            .all()
        )

        return session, messages

    def send_message(self, case_id: int, session_id: int, message: str) -> str:
        session = (
            self.db.query(models.ChatSession)
            .filter(
                models.ChatSession.id == session_id,
                models.ChatSession.case_id == case_id,
                models.ChatSession.closed == False
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=400,
                detail="Invalid or closed chat session"
            )

        # Save user message
        self.db.add(models.ChatMessage(
            session_id=session.id,
            role="user",
            content=message
        ))
        self.db.commit()

        # Generate answer
        qa = QAService(self.db)
        result = qa.answer_question(
            case_id=case_id,
            session_id=session.id,
            question=message
        )

        return result["answer"]
