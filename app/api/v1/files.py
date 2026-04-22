# app/api/v1/files.py

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.core.dependencies import get_db, require_role, get_current_user, require_case_access
from app.models.case_file import CaseFile, FileStatus
from app.models.case import Case
from app.services.file_service import FileService
from app.schemas.file import FileUploadResponse
from datetime import datetime
router = APIRouter()


# -------------------------
# UPLOAD (DRAFT)
# -------------------------
@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    case = Depends(require_case_access()),
):
    svc = FileService(db)
    result = await svc.handle_file_upload(case_id, file)

    if not result["saved"]:
        raise HTTPException(status_code=500, detail=result.get("message", "failed"))

    return result

@router.post("/{file_id}/train")
async def train_file(
    file_id: int,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    svc = FileService(db)

    file = svc.get_file_by_id(file_id)
    if not file:
        raise HTTPException(404, "File not found")

    case = db.query(Case).filter(Case.id == file.case_id).first()

    user_roles = [r.name for r in user.roles]
    print("User Roles:", user_roles)  # Debugging line
    # Access control
    if not (
        "ADMIN" in user_roles
        or case.owner_id == user.id
        or user in case.users
    ):
        raise HTTPException(403, "Access denied")

    # ❌ Prevent re-processing
    if file.status in [FileStatus.PROCESSING, FileStatus.PROCESSED]:
        raise HTTPException(400, "Already processed or processing")

    # 🔥 ADMIN FLOW
    if "ADMIN" in user_roles:
        if file.status == FileStatus.DRAFT:
            file.approved_by = user.id
            file.approved_at = datetime.utcnow()

        file.status = FileStatus.APPROVED
        db.commit()

        # 🚀 Let service handle PROCESSING → PROCESSED
        return await svc.process_file_embeddings_safe(file_id)

    # 👤 USER FLOW
    if file.status != FileStatus.DRAFT:
        raise HTTPException(400, "Already requested or processed")

    file.status = FileStatus.PENDING
    file.requested_by = user.id
    file.requested_at = datetime.utcnow()

    db.commit()

    return {"message": "Training request sent"}


@router.post("/{file_id}/approve")
async def approve_file(
    file_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_role(["ADMIN"]))
):
    svc = FileService(db)

    file = svc.get_file_by_id(file_id)
    if not file:
        raise HTTPException(404, "File not found")

    if file.status != FileStatus.PENDING:
        raise HTTPException(400, "Invalid state")

    file.status = FileStatus.APPROVED
    file.approved_by = user.id
    file.approved_at = datetime.utcnow()

    db.commit()

    # 🚀 IMPORTANT: service handles PROCESSING + PROCESSED
    return await svc.process_file_embeddings_safe(file_id)

# -------------------------
# VIEW FILE
# -------------------------
@router.get("/{file_id}/view")
def view_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    file_service = FileService(db)

    file = file_service.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    case = db.query(Case).filter(Case.id == file.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    user_roles = [r.name for r in current_user.roles]

    if (
        "ADMIN" in user_roles
        or "MASTER_ADMIN" in user_roles
        or case.owner_id == current_user.id
        or current_user in case.users
    ):
        return file_service.view_file(file_id)

    raise HTTPException(status_code=403, detail="Access denied")