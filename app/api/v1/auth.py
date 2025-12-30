# app/api/v1/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserOut
from app.core.dependencies import get_db
from app.services.auth_service import AuthService
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter()

@router.post("/register", response_model=UserOut)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user = svc.create_user(user_in)
    return user

@router.post("/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    svc = AuthService(db)

    token = svc.authenticate_user_and_get_tokens(
        email=form_data.username,   # IMPORTANT
        password=form_data.password
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
