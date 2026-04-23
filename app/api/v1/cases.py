# app/api/v1/cases.py
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Form, HTTPException,Query, UploadFile,File
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.core.dependencies import get_db
from app.models.case_file import CaseFile, FileStatus
from app.models.upcoming_meeting import UpcomingMeeting
from app.schemas.case import CreateCaseOut, CaseListOut,PaginatedResponse,CaseOut
from app.services.case_service import CaseService
from typing import List, Optional
from app.schemas.file import CaseFileNameOut
from app.core.dependencies import require_role, get_current_user
from app.models.user import User
from app.models.case import Case
from sqlalchemy.orm import joinedload
from app.schemas.file import ApprovalFileOut
from app.services.file_service import FileService

router = APIRouter()

@router.get("/required-approval-files", response_model=List[ApprovalFileOut])
def list_files_requiring_approval(
    db: Session = Depends(get_db),
    user=Depends(require_role(["ADMIN"]))
):
    # 🔥 Fetch files
    files = (
        db.query(CaseFile)
        .options(joinedload(CaseFile.case))
        .filter(CaseFile.status == FileStatus.PENDING)
        .all()
    )

    # 🔥 Collect user ids
    user_ids = list({f.requested_by for f in files if f.requested_by})

    users_map = {}

    if user_ids:
        users = (
            db.query(User)
            .options(joinedload(User.roles))  # ✅ preload roles
            .filter(User.id.in_(user_ids))
            .all()
        )
        users_map = {u.id: u for u in users}

    response = []

    for f in files:
        case = f.case
        requested_user = users_map.get(f.requested_by)

        response.append({
            "case_id": case.id,
            "case_name": case.case_name,
            "file_id": f.id,
            "file_name": f.filename,
            "requested_by": {
                "id": requested_user.id,
                "name": requested_user.full_name,
                "email": requested_user.email,
                "roles": [role.name for role in requested_user.roles]  # ✅ roles added
            } if requested_user else None
        })

    return response
@router.post("", response_model=CreateCaseOut)
async def create_case(
    case_name: str = Form(...),
    description: str | None = Form(None),
    manager_ids: List[int] = Form(...),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["ADMIN"])),
):
    svc = CaseService(db)
    hnd=FileService(db)
    # create case synchronously (keeps your existing create_case behavior)
    case = svc.create_case_from_fields(case_name=case_name, description=description)

    managers = db.query(User).filter(User.id.in_(manager_ids)).all()

    if not managers:
        raise HTTPException(400, "Invalid managers")

    for manager in managers:
        roles = [r.name for r in manager.roles]
        if "MANAGER" not in roles:
            raise HTTPException(400, f"{manager.email} is not a manager")

    case.managers.extend(managers)

    db.commit()
    db.refresh(case)

    file_out = None
    extracted_metadata = None

    if file:
        # 1) save file and DB record (async)
        file_upload_result = await hnd.handle_file_upload(case_id=case.id, uploaded_file=file)

        if not file_upload_result.get("saved"):
            # optional: delete case or keep it — here we keep the case and surface error
            # Decide behavior: you can rollback case if file is required.
            raise HTTPException(status_code=400, detail=f"File upload failed: {file_upload_result.get('message')}")

        file_id = file_upload_result["file_id"]

        # 2) create embeddings and process file (async)
        processing_result = await hnd.process_file_embeddings(file_id=file_id)
        print("File processing result:", processing_result)  # log the processing result for debugging
        if not processing_result.get("processed"):
            # continue and return partial result; or raise if you need strict success
            # we'll return partial result
            extracted_metadata = None
        else:
            # 3) Run QA/AI to extract structured metadata from saved chunks/embeddings
            try:
                print("i worked")
                extracted_metadata = svc.qa_service.extract_case_metadata_for_file(file_id=file_id)
                print("Extracted metadata:", extracted_metadata )
            except Exception as e:
                # log the error, return partial
                extracted_metadata = None

        # Build file_out to include in response
    if extracted_metadata:
        svc.save_case_metadata(case.id, extracted_metadata)

    return {
        "id": case.id,
        "case_name": case.case_name,
        "case_no": case.case_no,
        "description": case.description,
        "created_at": case.created_at,
    }

@router.get("/list-cases", response_model=PaginatedResponse[CaseListOut])
def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    case_name: Optional[str] = Query(None),
    case_no: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    service = CaseService(db)
    skip = (page - 1) * page_size

    total, cases = service.list_cases_filtered(
        skip=skip,
        limit=page_size,
        case_name=case_name,
        case_no=case_no,
        user=current_user,
    )

    # ✅ COUNT upcoming meetings (ONLY ONCE)
    total_upcoming_meetings = (
        db.query(func.count(UpcomingMeeting.id))
        .filter(
            UpcomingMeeting.start_time_utc > datetime.utcnow(),
            UpcomingMeeting.status == "scheduled"
        )
        .scalar()
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": cases,
        "total_upcoming_meetings": total_upcoming_meetings,  # 👈 ADD THIS
    }
    
@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["ADMIN","MANAGER", "MEMBER"])),
):
    svc = CaseService(db)

    case = svc.get_case_with_details(case_id)
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # ✅ Pydantic v2 serialization
    return CaseOut.model_validate(case, from_attributes=True)

@router.get("/{case_id}/files", response_model=List[CaseFileNameOut])
def list_case_files(
    case_id: int,
    db: Session = Depends(get_db),
    _ = Depends(require_role(["MASTER_ADMIN", "ADMIN"])),
):
    """
    List file names for a case (id + filename only)
    """
    file_service = FileService(db)
    return file_service.list_file_names_by_case(case_id)

@router.post("/{case_id}/assign-users")
def assign_users(
    case_id: int,
    user_ids: list[int] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        raise HTTPException(404, "Case not found")

    user_roles = [r.name for r in current_user.roles]

    # Only ADMIN or MANAGER (owner) can assign
    if "ADMIN" not in user_roles and current_user not in case.managers:
        raise HTTPException(403, "Not allowed")

    users = db.query(User).filter(User.id.in_(user_ids)).all()

    if not users:
        raise HTTPException(400, "Invalid users")

    # 🔥 IMPORTANT: Ensure only USERS (not managers/admins)
    for user in users:
        if user in case.users:
            continue  # skip already assigned users
        roles = [r.name for r in user.roles]
        if "MEMBER" not in roles:
            raise HTTPException(400, f"{user.email} is not a normal user")

    case.users.extend(users)
    db.commit()

    return {"message": "Users assigned successfully"}

@router.post("/{case_id}/assign-managers")
def assign_managers(
    case_id: int,
    manager_ids: list[int] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["ADMIN"]))
):
    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        raise HTTPException(404, "Case not found")

    managers = db.query(User).filter(User.id.in_(manager_ids)).all()

    if not managers:
        raise HTTPException(400, "Invalid managers")

    for manager in managers:
        roles = [r.name for r in manager.roles]

        if "MANAGER" not in roles:
            raise HTTPException(400, f"{manager.email} is not a manager")

        if manager in case.managers:
            continue

        case.managers.append(manager)

    db.commit()

    return {"message": "Managers assigned successfully"}
