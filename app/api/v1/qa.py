# app/api/v1/qa.py
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.schemas.qa import QARequest, QAResponse, SpeechResponse
from app.services.qa_service import QAService
from app.core.global_case import global_case

router = APIRouter()

@router.post("/ask", response_model=QAResponse)
def ask_question(
    payload: QARequest,
    db: Session = Depends(get_db),
):
    service = QAService(db)
    result = service.answer_voice_question(
        case_id=payload.case_id,
        question=payload.question,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No answer found for the given question",
        )
    return result

@router.post("/speech-to-text", response_model=SpeechResponse)
async def speech_to_text(file: UploadFile = File(...)
                         ,db: Session = Depends(get_db)):
    service = QAService(db)
    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid audio file")


    result = await service.process_audio_file(file)
    return result

@router.post("/ask_voice")
def ask(data: dict, db: Session = Depends(get_db)):

    case_id = global_case.case_id
    transcript_lines = data.get("transcript", [])

    transcript = "\n".join(transcript_lines)
    print(transcript, "   transcript for testing bot qa")
    
    service = QAService(db)

    result = service.answer_voice_question(
        case_id=case_id,
        question=transcript
    )
    
    print(result, "result for testing bot qa")
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No answer found for the given question",
        )

    # ✅ convert everything to string
    return {
        "answer": str(result.get("answer", "")),
        "source_chunks": str(result.get("source_chunks", ""))
    }
