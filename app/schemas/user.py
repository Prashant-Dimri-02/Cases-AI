# app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import List, Optional

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] 

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    roles: List[str]

    class Config:
        from_attributes = True
        
class MakeManagerRequest(BaseModel):
    user_id: int