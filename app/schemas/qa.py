# app/schemas/qa.py
from pydantic import BaseModel

class QARequest(BaseModel):
    case_id: int
    question: str

class QAResponse(BaseModel):
    answer: str
    source_chunks: list


class SpeechResponse(BaseModel):
    text: str
    confidence: float | None = None
    language: str | None = None
    duration_ms: int | None = None
    provider: str = "azure"