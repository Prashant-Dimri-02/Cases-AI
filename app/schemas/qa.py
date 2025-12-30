# app/schemas/qa.py
from pydantic import BaseModel

class QARequest(BaseModel):
    case_id: int
    question: str

class QAResponse(BaseModel):
    answer: str
    source_chunks: list
