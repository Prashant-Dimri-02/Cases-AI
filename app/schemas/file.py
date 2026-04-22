# app/schemas/file.py
from pydantic import BaseModel
from typing import List, Optional

class FileUploadResponse(BaseModel):
    file_id: int
    saved: bool
    message: str
    file_path: Optional[str] = None
class CaseFileNameOut(BaseModel):
    id: int
    filename: str
    status: str
    file_size: int
    
    class Config:
        from_attributes = True
        
class RequestedByUserOut(BaseModel):
    id: int
    name: Optional[str]
    email: Optional[str]
    roles: List[str]

    class Config:
        orm_mode = True
        
class ApprovalFileOut(BaseModel):
    case_id: int
    case_name: str

    file_id: int
    file_name: Optional[str]

    requested_by: Optional[RequestedByUserOut]

    class Config:
        orm_mode = True