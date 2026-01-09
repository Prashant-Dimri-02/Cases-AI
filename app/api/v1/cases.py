# app/api/v1/cases.py
from fastapi import APIRouter, Depends, Form, HTTPException,Query, UploadFile,File
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_admin
from app.schemas.case import CreateCaseOut, CaseListOut,PaginatedResponse,CaseOut
from app.services.case_service import CaseService
from typing import List, Optional
from app.schemas.file import CaseFileNameOut

from app.services.file_service import FileService

router = APIRouter()

@router.post("", response_model=CreateCaseOut)
async def create_case(
    case_name: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin),
):
    svc = CaseService(db)
    hnd=FileService(db)
    # create case synchronously (keeps your existing create_case behavior)
    case = svc.create_case_from_fields(case_name=case_name, description=description)

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

        if not processing_result.get("processed"):
            # continue and return partial result; or raise if you need strict success
            # we'll return partial result
            extracted_metadata = None
        else:
            # 3) Run QA/AI to extract structured metadata from saved chunks/embeddings
            try:
                extracted_metadata = svc.qa_service.extract_case_metadata_for_file(file_id=file_id)
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

    case_name: Optional[str] = Query(None, description="Search by case name"),
    case_no: Optional[str] = Query(None, description="Exact case number"),

    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    service = CaseService(db)
    skip = (page - 1) * page_size

    total, cases = service.list_cases_filtered(
        skip=skip,
        limit=page_size,
        case_name=case_name,
        case_no=case_no,
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": cases,
    }

@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    svc = CaseService(db)

    case = svc.get_case_with_details(case_id)
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    print(case.__dict__)
    print("here it is")
    # ✅ Pydantic v2 serialization
    return CaseOut.model_validate(case, from_attributes=True)

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