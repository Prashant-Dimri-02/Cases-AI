# app/api/v1/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_role
from app.models.role import Role
from app.models.user import User
from app.services.auth_service import AuthService
from app.schemas.user import UserOut

router = APIRouter()

@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_role(["ADMIN"]))):
    svc = AuthService(db)
    return svc.list_users()

@router.post("/{user_id}/make-manager")
def make_manager(
    user_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["ADMIN"]))
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(404, "User not found")

    manager_role = db.query(Role).filter(Role.name == "MANAGER").first()

    if not manager_role:
        raise HTTPException(500, "MANAGER role not found")

    # 🔥 Remove all existing roles (since you want single role)
    user.roles.clear()

    # Assign MANAGER role
    user.roles.append(manager_role)

    db.commit()
    db.refresh(user)

    return {
        "message": f"{user.email} promoted to MANAGER"
    }
