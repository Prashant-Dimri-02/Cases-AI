# app/services/auth_service.py
from sqlalchemy.orm import Session
from app import models
from app.schemas.user import UserCreate
from app.utils.password import get_password_hash, verify_password
from app.core.security import create_access_token, create_refresh_token
from app.schemas.auth import Token

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, payload: UserCreate):
        user = self.db.query(models.user.User).filter(models.user.User.email == payload.email).first()
        if user:
            raise ValueError("User exists")
        hashed = get_password_hash(payload.password)
        new = models.user.User(email=payload.email, hashed_password=hashed, full_name=payload.full_name)
        # first user becomes admin if no users exist (simple convenience)
        if self.db.query(models.user.User).count() == 0:
            new.is_admin = True
        self.db.add(new)
        self.db.commit()
        self.db.refresh(new)
        return new

    def authenticate_user_and_get_tokens(self, email: str, password: str):
        user = self.db.query(models.user.User).filter(models.user.User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return None
        access = create_access_token(subject=str(user.id))
        refresh = create_refresh_token(subject=str(user.id))
        # persist refresh token
        rt = models.refresh_token.RefreshToken(user_id=user.id, token=refresh)
        self.db.add(rt)
        self.db.commit()
        return {"access_token": access, "token_type": "bearer", "refresh_token": refresh}   

    def list_users(self):
        return self.db.query(models.user.User).all()
