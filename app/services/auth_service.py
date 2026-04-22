from sqlalchemy.orm import Session
from app import models
from app.schemas.user import UserCreate
from app.utils.password import get_password_hash, verify_password
from app.core.security import create_access_token, create_refresh_token


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, payload: UserCreate):
        existing = self.db.query(models.user.User).filter(
            models.user.User.email == payload.email
        ).first()

        if existing:
            raise ValueError("User exists")

        hashed = get_password_hash(payload.password)

        new_user = models.user.User(
            email=payload.email,
            hashed_password=hashed,
            full_name=payload.full_name
        )

        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        # ✅ Assign default role = MEMBER
        role = self.db.query(models.role.Role).filter_by(name="MEMBER").first()
        if role:
            new_user.roles.append(role)
            self.db.commit()
            self.db.refresh(new_user)

        # ✅ IMPORTANT: Return serialized response
        return {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "roles": [r.name for r in new_user.roles],
        }
 
    def authenticate_user_and_get_tokens(self, email: str, password: str):
        user = self.db.query(models.user.User).filter(
            models.user.User.email == email
        ).first()

        if not user or not verify_password(password, user.hashed_password):
            return None

        # ✅ extract roles
        role_names = [role.name for role in user.roles]

        access = create_access_token(
            subject=str(user.id)
        )

        refresh = create_refresh_token(subject=str(user.id))

        rt = models.refresh_token.RefreshToken(
            user_id=user.id,
            token=refresh
        )

        self.db.add(rt)
        self.db.commit()

        return {
            "access_token": access,
            "token_type": "bearer",
            "refresh_token": refresh,
            "roles": role_names  # useful for frontend
            }

    def list_users(self):
        users = self.db.query(models.user.User).all()

        result = []
        for u in users:
            result.append({
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "roles": [r.name for r in u.roles],
            })

        return result