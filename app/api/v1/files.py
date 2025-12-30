# app/api/v1/files.py
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException,BackgroundTasks
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_admin
from app.services.file_service import FileService
from app.schemas.file import FileUploadResponse
from fastapi.responses import FileResponse

router = APIRouter()

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    svc = FileService(db)
    result = await svc.handle_file_upload(case_id, file)
    if not result["saved"]:
        raise HTTPException(status_code=500, detail=result.get("message", "failed"))
    return result

@router.post("/train")
async def train_file_embeddings(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Train / generate embeddings for an uploaded file
    """
    file_service = FileService(db)

    # optional safety check
    file = file_service.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    if file.processed:
        return {
            "processed": True,
            "file_id": file_id,
            "message": "File already processed",
        }

    # Run embedding in background
    background_tasks.add_task(
        file_service.process_file_embeddings,
        file_id,
    )

    return {
        "started": True,
        "file_id": file_id,
        "message": "Embedding process started",
    }

@router.get("/{file_id}/view")
def view_file(
    file_id: int,
    db: Session = Depends(get_db),
):
    file_service = FileService(db)
    return file_service.view_file(file_id)