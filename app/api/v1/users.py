# app/api/v1/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_admin
from app.services.auth_service import AuthService
from app.schemas.user import UserOut

router = APIRouter()

@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_admin)):
    svc = AuthService(db)
    return svc.list_users()
