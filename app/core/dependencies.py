# app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.db.session import SessionLocal
from sqlalchemy.orm import Session
from app.models.case import Case
from app.core.security import decode_token
from app.models.user import User
from app import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    user = db.query(models.user.User).filter(models.user.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def require_role(required_roles: list[str]):
    def checker(current_user: User = Depends(get_current_user)):
        user_roles = [role.name for role in current_user.roles]

        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Required roles: {required_roles}"
            )
        return current_user
    return checker

def require_case_access():
    def checker(
        case_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        case = db.query(Case).filter(Case.id == case_id).first()

        if not case:
            raise HTTPException(404, "Case not found")

        user_roles = [r.name for r in current_user.roles]

        # ADMIN → full access
        if "ADMIN" in user_roles or "MASTER_ADMIN" in user_roles:
            return case

        # MANAGER → full access
        if current_user in case.managers:
            return case

        # MEMBER → assigned users
        if current_user in case.users:
            return case

        raise HTTPException(403, "Access denied")

    return checker