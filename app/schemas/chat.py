# app/schemas/chat.py
from pydantic import BaseModel
from typing import List

class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: str

class OpenChatResponse(BaseModel):
    session_id: int
    messages: List[ChatMessageOut]

class OpenChatRequest(BaseModel):
    user_id: int

class ChatMessageRequest(BaseModel):
    message: str
    session_id: int

class ChatMessageResponse(BaseModel):
    answer: str
    session_id: int
