# app/services/file_service.py

import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Set

from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
import aiofiles

from app import models
from app.utils.pdf_parser import extract_text_from_file_path
from app.utils.text_chunker import chunk_text
from app.models.case_file import CaseFile, FileStatus
from app.services.embedding_service import EmbeddingService
from app.core.config import settings


class FileService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # -------------------------
    # FILE UPLOAD (DRAFT)
    # -------------------------
    async def handle_file_upload(self, case_id: int, uploaded_file: UploadFile):

        allowed_mime: Set[str] = getattr(
            settings,
            "ALLOWED_UPLOAD_MIME_TYPES",
            {
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
            },
        )

        allowed_exts = {".pdf", ".docx", ".doc"}

        content_type = (uploaded_file.content_type or "").lower()
        original_filename = os.path.basename(uploaded_file.filename or "file")
        data = await uploaded_file.read()
        size = len(data)

        if size == 0:
            return {"saved": False, "message": "Empty file"}

        if getattr(settings, "MAX_UPLOAD_SIZE_BYTES", None) and size > settings.MAX_UPLOAD_SIZE_BYTES:
            return {"saved": False, "message": "File too large"}

        if allowed_mime and content_type not in allowed_mime:
            return {"saved": False, "message": f"Unsupported MIME: {content_type}"}

        ext = Path(original_filename).suffix.lower()
        if not ext:
            mime_to_ext = {
                "application/pdf": ".pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/msword": ".doc",
            }
            ext = mime_to_ext.get(content_type, "")

        if ext not in allowed_exts:
            return {"saved": False, "message": f"Unsupported extension: {ext}"}

        unique_name = f"{uuid.uuid4().hex}{ext}"
        upload_dir = Path(settings.UPLOAD_DIR)
        local_path = upload_dir / unique_name

        try:
            async with aiofiles.open(local_path, "wb") as f:
                await f.write(data)
        except Exception as e:
            return {"saved": False, "message": f"File save error: {e}"}

        file_model = CaseFile(
            case_id=case_id,
            filename=original_filename,
            file_path=unique_name,
            content_type=content_type,
            file_size=size,
            status=FileStatus.DRAFT,
        )

        try:
            self.db.add(file_model)
            self.db.commit()
            self.db.refresh(file_model)
        except Exception as e:
            local_path.unlink(missing_ok=True)
            return {"saved": False, "message": f"DB error: {e}"}

        return {
            "file_id": file_model.id,
            "saved": True,
            "message": "File uploaded successfully",
            "file_path": f"/uploads/{unique_name}",
        }

    # -------------------------
    # LIST FILES
    # -------------------------
    def list_file_names_by_case(self, case_id: int):
        return (
            self.db.query(
                CaseFile.id,
                CaseFile.filename,
                CaseFile.status,
                CaseFile.file_size
            )
            .filter(CaseFile.case_id == case_id)
            .order_by(CaseFile.created_at.desc())
            .all()
        )

    # -------------------------
    # REQUEST TRAINING
    # -------------------------
    def request_training(self, file_id: int, user_id: int):

        file = self.get_file_by_id(file_id)

        if not file:
            raise HTTPException(404, "File not found")

        if file.status != FileStatus.DRAFT:
            raise HTTPException(400, "Already requested or processed")

        file.status = FileStatus.PENDING
        file.requested_by = user_id
        file.requested_at = datetime.utcnow()

        self.db.commit()

        return {"message": "Training request sent to admin"}

    # -------------------------
    # PROCESS EMBEDDINGS
    # -------------------------
    async def process_file_embeddings_safe(self, file_id: int):

        file = (
            self.db.query(CaseFile)
            .filter(CaseFile.id == file_id)
            .with_for_update()
            .first()
        )

        if not file:
            raise HTTPException(404, "File not found")

        if file.status == FileStatus.PROCESSED:
            return {"message": "Already processed"}

        if file.status == FileStatus.PROCESSING:
            return {"message": "Already processing"}

        if file.status != FileStatus.APPROVED:
            raise HTTPException(400, "File not approved")

        try:
            file.status = FileStatus.PROCESSING
            self.db.commit()

            abs_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, file.file_path))

            if not os.path.exists(abs_path):
                file.status = FileStatus.REJECTED
                self.db.commit()
                raise HTTPException(404, "File missing on disk")

            text = extract_text_from_file_path(abs_path)

            if not text:
                file.status = FileStatus.REJECTED
                self.db.commit()
                return {"message": "No text found"}

            chunks = chunk_text(text, chunk_size=800, overlap=100)
            embeddings = self.embedding_service.create_embeddings_for_chunks(chunks)

            for chunk, vector in zip(chunks, embeddings):
                emb = models.embedding.Embedding(
                    file_id=file.id,
                    chunk_text=chunk,
                    vector=vector,
                )
                self.db.add(emb)

            file.status = FileStatus.PROCESSED
            file.processed_at = datetime.utcnow()

            self.db.commit()

            return {"processed": True}

        except Exception as e:
            self.db.rollback()
            file.status = FileStatus.REJECTED
            self.db.commit()
            raise e

    # -------------------------
    # GET FILE
    # -------------------------
    def get_file_by_id(self, file_id: int):
        return (
            self.db.query(CaseFile)
            .filter(CaseFile.id == file_id)
            .first()
        )

    # -------------------------
    # VIEW FILE
    # -------------------------
    def view_file(self, file_id: int):

        file = self.get_file_by_id(file_id)

        if not file:
            raise HTTPException(404, "File not found")

        file_path = os.path.join(settings.UPLOAD_DIR, file.file_path)

        if not os.path.exists(file_path):
            raise HTTPException(404, "File missing on disk")

        ext = Path(file.file_path).suffix.lower()

        if ext == ".pdf":
            media_type = "application/pdf"
            disposition = "inline"
        elif ext == ".docx":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disposition = "attachment"
        elif ext == ".doc":
            media_type = "application/msword"
            disposition = "attachment"
        else:
            media_type = file.content_type or "application/octet-stream"
            disposition = "attachment"

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file.filename,
            headers={
                "Content-Disposition": f'{disposition}; filename="{file.filename}"'
            },
        )