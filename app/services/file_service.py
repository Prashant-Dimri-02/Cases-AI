# app/services/file_service.py
import os
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import UploadFile,HTTPException
from app import models
from app.utils.pdf_parser import extract_text_from_pdf_path
from app.utils.text_chunker import chunk_text
from app.models.case_file import CaseFile
from app.services.embedding_service import EmbeddingService
from app.core.config import settings
from fastapi.responses import FileResponse

class FileService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        # ensure dir exists
        Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    async def handle_file_upload(self, case_id: int, uploaded_file: UploadFile):
        # -------------------
        # Validation
        # -------------------
        content_type = uploaded_file.content_type
        data = await uploaded_file.read()
        size = len(data)

        if size == 0:
            return {"saved": False, "message": "Empty file"}

        if size > settings.MAX_UPLOAD_SIZE_BYTES:
            return {"saved": False, "message": "File too large"}

        if settings.ALLOWED_UPLOAD_TYPES and content_type != settings.ALLOWED_UPLOAD_TYPES:
            return {"saved": False, "message": f"Unsupported file type: {content_type}"}

        # -------------------
        # Save file to disk
        # -------------------
        ext = Path(uploaded_file.filename).suffix or ".pdf"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        local_path = os.path.join(settings.UPLOAD_DIR, unique_name)

        with open(local_path, "wb") as f:
            f.write(data)

        # -------------------
        # Save DB record ONLY
        # -------------------
        file_model = models.case_file.CaseFile(
            case_id=case_id,
            filename=uploaded_file.filename,
            file_path=unique_name,
            content_type=content_type,
            file_size=size,
            processed=False,
        )

        self.db.add(file_model)
        self.db.commit()
        self.db.refresh(file_model)

        return {
            "file_id": file_model.id,
            "saved": True,
            "message": "File uploaded successfully",
            "file_path": f"/uploads/{unique_name}",
        }


    def list_file_names_by_case(self, case_id: int):
        return (
            self.db.query(CaseFile.id, CaseFile.filename,CaseFile.processed)
            .filter(CaseFile.case_id == case_id)
            .order_by(CaseFile.created_at.desc())
            .all()
        )
        
        
    async def process_file_embeddings(self, file_id: int):
        # -------------------
        # Fetch file record
        # -------------------
        print("hello i worked")
        file_model = (
            self.db.query(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.id == file_id)
            .first()
        )

        if not file_model:
            raise ValueError("File not found")

        abs_path = os.path.abspath(
            os.path.join(settings.UPLOAD_DIR, file_model.file_path)
        )

        # -------------------
        # Extract text
        # -------------------
        text = extract_text_from_pdf_path(abs_path)
        if not text.strip():
            return {"processed": False, "message": "No text found in PDF"}

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
        View / download a PDF file by file_id
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

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=file.filename,
            headers={
                "Content-Disposition": f'inline; filename="{file.filename}"'
            },
        )
        