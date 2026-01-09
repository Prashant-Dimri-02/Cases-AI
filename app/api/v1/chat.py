# app/api/v1/chat.py
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.chat import (
    OpenChatRequest,
    OpenChatResponse,
    ChatMessageRequest,
    ChatMessageResponse
)
from app.services.chat_service import ChatService

router = APIRouter(tags=["Chat"])


@router.post("/open", response_model=OpenChatResponse)
def open_chat(
    caseid: int = Header(...),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    session, messages = service.open_session(caseid)

    return {
        "session_id": session.id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    }


@router.post("/message", response_model=ChatMessageResponse)
def send_message(
    payload: ChatMessageRequest,
    caseid: int = Header(...),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    answer = service.send_message(
        case_id=caseid,
        session_id=payload.session_id,
        message=payload.message
    )
    return {
        "answer": answer,
        "session_id": payload.session_id
    }
