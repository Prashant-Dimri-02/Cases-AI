# app/api/v1/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user, get_db, require_role
from app.models.role import Role
from app.models.user import User
from app.services.auth_service import AuthService
from app.schemas.user import UserOut,MakeManagerRequest

router = APIRouter()

@router.get("/list", response_model=list[UserOut])
def list_users(
    case_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    svc = AuthService(db)
    return svc.list_users(current_user, case_id)

@router.post("/make-manager")
def make_manager(
    payload: MakeManagerRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    svc = AuthService(db)
    return svc.make_manager(current_user, payload.user_id)

@router.get("/assignable-users", response_model=list[UserOut])
def get_assignable_users(
    case_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    svc = AuthService(db)
    return svc.get_assignable_users(current_user, case_id)

@router.get("/assignable-managers", response_model=list[UserOut])
def get_assignable_managers(
    case_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    svc = AuthService(db)
    return svc.get_assignable_managers(current_user, case_id)