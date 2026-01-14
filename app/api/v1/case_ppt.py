from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.services.case_ppt_service import CasePPTService
from fastapi.responses import FileResponse

router = APIRouter(prefix="/cases", tags=["Case PPT"])


@router.post("/{case_id}/generate-ppt")
def generate_case_ppt(
    case_id: int,
    db: Session = Depends(get_db),
):
    service = CasePPTService(db)
    file_path = service.generate_case_ppt(case_id)

    return FileResponse(
        path=file_path,
        filename="Case_Presentation.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
