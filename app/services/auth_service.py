from fastapi import HTTPException
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

    def list_users(self, current_user, case_id: int | None = None):
        current_roles = {r.name for r in current_user.roles}

        query = self.db.query(models.user.User).join(models.user.User.roles)

        # ADMIN → all users + managers
        if "ADMIN" in current_roles:
            users = query.filter(
                models.role.Role.name.in_(["MEMBER", "MANAGER"])
            ).distinct().all()

        # MANAGER → all users
        elif "MANAGER" in current_roles:
            users = query.filter(
                models.role.Role.name == "MEMBER"
            ).distinct().all()

        # MEMBER → same case users
        elif "MEMBER" in current_roles:
            if not case_id:
                return []

            users = (
                query
                .join(models.associations_case_user.case_users)
                .filter(
                    models.associations_case_user.case_users.c.case_id == case_id,
                    models.role.Role.name == "MEMBER"
                )
                .distinct()
                .all()
            )
        else:
            users = []

        return self.format_users(users)
    
    def get_assignable_users(self, current_user, case_id: int):
        current_roles = {r.name for r in current_user.roles}

        # Only ADMIN or MANAGER can assign
        if "ADMIN" not in current_roles and "MANAGER" not in current_roles:
            raise HTTPException(403, "Not allowed")

        query = (
            self.db.query(models.user.User)
            .join(models.user.User.roles)
            .filter(models.role.Role.name == "MEMBER")
        )

        # Optional: exclude already assigned users
        query = query.outerjoin(
            models.associations_case_user.case_users,
            (models.associations_case_user.case_users.c.user_id == models.user.User.id) &
            (models.associations_case_user.case_users.c.case_id == case_id)
        ).filter(
            models.associations_case_user.case_users.c.user_id == None
        )

        users = query.distinct().all()

        return self.format_users(users)
    
    def get_assignable_managers(self, current_user, case_id: int):
        current_roles = {r.name for r in current_user.roles}

        # Only ADMIN can assign managers
        if "ADMIN" not in current_roles:
            raise HTTPException(403, "Not allowed")

        query = (
            self.db.query(models.user.User)
            .join(models.user.User.roles)
            .filter(models.role.Role.name == "MANAGER")
        )

        # Optional: exclude already assigned managers
        case = self.db.query(models.case.Case).filter(models.case.Case.id == case_id).first()

        if not case:
            raise HTTPException(404, "Case not found")

        existing_manager_ids = [m.id for m in case.managers]

        if existing_manager_ids:
            query = query.filter(~models.user.User.id.in_(existing_manager_ids))

        users = query.distinct().all()

        return self.format_users(users)
    
    def format_users(self, users):
        return [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "roles": [r.name for r in u.roles],
            }
            for u in users
        ]