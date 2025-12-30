# app/schemas/case.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CaseCreate(BaseModel):
    case_name: str
    description: Optional[str] = None

class CaseOut(BaseModel):
    id: int
    case_name: str
    case_no: str
    description: Optional[str]

    class Config:
        orm_mode = True

class CaseListOut(BaseModel):
    id: int
    case_name: str
    case_no: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2
