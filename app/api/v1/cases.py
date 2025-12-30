# app/api/v1/cases.py
from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_admin
from app.schemas.case import CaseCreate, CaseOut, CaseListOut
from app.services.case_service import CaseService
from typing import List
from app.schemas.file import CaseFileNameOut

from app.services.file_service import FileService

router = APIRouter()

@router.post("", response_model=CaseOut)
def create_case(payload: CaseCreate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    svc = CaseService(db)
    case = svc.create_case(payload)
    return case

@router.get("/list-cases", response_model=List[CaseListOut])
def list_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    _ = Depends(require_admin)
):
    """
    List all cases (Admin only)
    """
    service = CaseService(db)
    return service.list_cases(skip=skip, limit=limit)

@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    svc = CaseService(db)
    c = svc.get_case(case_id)
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    return c

@router.get("/{case_id}/files", response_model=List[CaseFileNameOut])
def list_case_files(
    case_id: int,
    db: Session = Depends(get_db),
    _ = Depends(require_admin),
):
    """
    List file names for a case (id + filename only)
    """
    file_service = FileService(db)
    return file_service.list_file_names_by_case(case_id)