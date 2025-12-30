# app/schemas/file.py
from pydantic import BaseModel
from typing import Optional

class FileUploadResponse(BaseModel):
    file_id: int
    saved: bool
    message: str
    file_path: Optional[str] = None
class CaseFileNameOut(BaseModel):
    id: int
    filename: str
    processed: bool
    
    class Config:
        from_attributes = True