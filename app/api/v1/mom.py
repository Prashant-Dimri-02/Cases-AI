# app/api/v1/mom.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.services.mom_service import MOMService
from app.core.global_case import global_case

router = APIRouter()

@router.post("/generate_mom")
def generate_mom(data: dict, db: Session = Depends(get_db)):
    
    transcript_lines = data.get("transcript", [])
    print(transcript_lines, "   transcript for testing bot mom")  # Debug print
    if not transcript_lines:
        raise HTTPException(status_code=400, detail="Transcript is empty")

    transcript = "\n".join(transcript_lines)

    service = MOMService(db)

    result = service.generate_mom(
        case_id=global_case.case_id,
        transcript=transcript
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to generate MOM")

    return result