# app/services/file_service.py
import os
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from app import models
from app.utils.pdf_parser import extract_text_from_file_path
from app.utils.text_chunker import chunk_text
from app.models.case_file import CaseFile
from app.services.embedding_service import EmbeddingService
from app.core.config import settings
from fastapi.responses import FileResponse
from typing import Set
import aiofiles


class FileService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        # ensure dir exists
        Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    async def handle_file_upload(self, case_id: int, uploaded_file: UploadFile):
        # -------------------
        # Config / allowed types
        # -------------------
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

        # -------------------
        # Basic meta + read
        # -------------------
        content_type = (uploaded_file.content_type or "").lower()
        original_filename = os.path.basename(uploaded_file.filename or "file")
        data = await uploaded_file.read()
        size = len(data)

        # -------------------
        # Validation
        # -------------------
        if size == 0:
            return {"saved": False, "message": "Empty file"}

        if getattr(settings, "MAX_UPLOAD_SIZE_BYTES", None) is not None and size > settings.MAX_UPLOAD_SIZE_BYTES:
            return {"saved": False, "message": "File too large"}

        # Validate by MIME type if configured
        if allowed_mime and content_type not in allowed_mime:
            return {"saved": False, "message": f"Unsupported file type (MIME): {content_type}"}

        # Validate extension (fallback / extra check)
        ext = Path(original_filename).suffix.lower()
        if not ext:
            # infer extension from content type if filename has no suffix
            mime_to_ext = {
                "application/pdf": ".pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/msword": ".doc",
            }
            ext = mime_to_ext.get(content_type, "")
        if ext not in allowed_exts:
            return {"saved": False, "message": f"Unsupported file extension: {ext or 'unknown'}"}

        # -------------------
        # Save file to disk (async)
        # -------------------
        unique_name = f"{uuid.uuid4().hex}{ext}"
        upload_dir = Path(getattr(settings, "UPLOAD_DIR", "uploads"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        local_path = upload_dir / unique_name

        try:
            async with aiofiles.open(local_path, "wb") as f:
                await f.write(data)
        except Exception as e:
            return {"saved": False, "message": f"Failed to save file: {e}"}

        # -------------------
        # Save DB record ONLY
        # -------------------
        file_model = models.case_file.CaseFile(
            case_id=case_id,
            filename=original_filename,
            file_path=unique_name,
            content_type=content_type,
            file_size=size,
            processed=False,
        )

        try:
            self.db.add(file_model)
            self.db.commit()
            self.db.refresh(file_model)
        except Exception as e:
            # Attempt cleanup if db save failed
            try:
                local_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {"saved": False, "message": f"DB error saving file record: {e}"}

        return {
            "file_id": file_model.id,
            "saved": True,
            "message": "File uploaded successfully",
            "file_path": f"/uploads/{unique_name}",
        }

    def list_file_names_by_case(self, case_id: int):
        return (
            self.db.query(CaseFile.id, CaseFile.filename, CaseFile.processed,CaseFile.file_size)
            .filter(CaseFile.case_id == case_id)
            .order_by(CaseFile.created_at.desc())
            .all()
        )

    async def process_file_embeddings(self, file_id: int):
        # -------------------
        # Fetch file record
        # -------------------
        file_model = (
            self.db.query(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.id == file_id)
            .first()
        )
        print(file_id)
        if not file_model:
            raise ValueError("File not found")

        abs_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, file_model.file_path))

        # -------------------
        # Extract text (now supports PDF and DOCX/DOC)
        # -------------------
        text = extract_text_from_file_path(abs_path)
        if not text or not text.strip():
            return {"processed": False, "message": "No text found in file"}

        chunks = chunk_text(text, chunk_size=800, overlap=100)

        # -------------------
        # Create embeddings
        # -------------------
        embeddings = self.embedding_service.create_embeddings_for_chunks(chunks)
        # -------------------
        # Save embeddings
        # -------------------
        for chunk, vector in zip(chunks, embeddings):
            emb = models.embedding.Embedding(
                file_id=file_model.id,
                chunk_text=chunk,
                vector=vector,
            )
            self.db.add(emb)

        file_model.processed = True
        self.db.commit()

        return {
            "processed": True,
            "file_id": file_model.id,
            "chunks": len(chunks),
            "message": "Embeddings created successfully",
        }

    def get_file_by_id(self, file_id: int):
        return (
            self.db.query(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.id == file_id)
            .first()
        )

    def view_file(self, file_id: int):
        """
        View / download a file by file_id
        """
        file = (
            self.db.query(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.id == file_id)
            .first()
        )

        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        file_path = os.path.join(settings.UPLOAD_DIR, file.file_path)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File missing on disk")

        # Determine media type from extension
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

