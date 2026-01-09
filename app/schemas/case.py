# app/schemas/case.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from typing import Generic, TypeVar, List
from datetime import date
T = TypeVar("T")

class ExtractedCaseMetadata(BaseModel):
    parties: Optional[str] = None
    court_name: Optional[str] = None
    filing_date: Optional[date] = None
    judge: Optional[str] = None
    attorney: Optional[str] = None
    next_court_date: Optional[date] = None
    strong_evidence: Optional[str] = None
    approaching_deadline: Optional[bool] = None
    case_description: Optional[str] = None
    
    model_config = {"from_attributes": True}

class CaseFileOut(BaseModel):
    id: int
    filename: str
    file_path: Optional[str]
    content_type: Optional[str]
    file_size: Optional[int]
    processed: bool

    model_config = {"from_attributes": True}

class CaseOut(BaseModel):
    id: int
    case_name: str
    description: Optional[str]
    case_no: str
    created_at: Optional[datetime]

    files: list[CaseFileOut] = []
    case_metadata: Optional[ExtractedCaseMetadata] = None

    model_config = {"from_attributes": True}

class CreateCaseOut(BaseModel):
    id: int
    case_name: str
    case_no: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2

class CaseListOut(BaseModel):
    id: int
    case_name: str
    case_no: str
    description: Optional[str]
    created_at: datetime
    case_metadata: Optional[ExtractedCaseMetadata] = None

    class Config:
        from_attributes = True  # Pydantic v2
        
class PaginatedResponse(BaseModel, Generic[T]):
    page: int
    page_size: int
    total: int
    items: List[T]