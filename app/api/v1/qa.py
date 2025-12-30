# app/api/v1/qa.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.schemas.qa import QARequest, QAResponse
from app.services.qa_service import QAService

router = APIRouter()

@router.post("/ask", response_model=QAResponse)
def ask_question(payload: QARequest, db: Session = Depends(get_db)):
    svc = QAService(db)
    answer = svc.answer_question(payload.case_id, payload.question)
    if not answer:
        raise HTTPException(status_code=404, detail="No answer")
    return answer
