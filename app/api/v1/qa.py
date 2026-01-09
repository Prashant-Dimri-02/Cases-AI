# app/api/v1/qa.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.schemas.qa import QARequest, QAResponse
from app.services.qa_service import QAService

router = APIRouter()

@router.post("/ask", response_model=QAResponse)
def ask_question(
    payload: QARequest,
    db: Session = Depends(get_db),
):
    service = QAService(db)
    result = service.answer_question(
        case_id=payload.case_id,
        question=payload.question,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No answer found for the given question",
        )

    return result

