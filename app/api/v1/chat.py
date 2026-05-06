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
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(tags=["Chat"])


@router.post("/open", response_model=OpenChatResponse)
def open_chat(
    caseid: int = Header(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    session, messages = service.open_session(
        caseid,
        current_user.id
    )

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ):
    service = ChatService(db)
    answer = service.send_message(
        case_id=caseid,
        user_id=current_user.id,
        session_id=payload.session_id,
        message=payload.message
    )
    return {
        "answer": answer,
        "session_id": payload.session_id
    }
