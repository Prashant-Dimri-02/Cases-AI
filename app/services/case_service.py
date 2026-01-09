# app/services/case_service.py
from typing import Optional
from sqlalchemy.orm import Session,joinedload
import datetime

from app import models
from app.models.case import Case
from app.models.case_metadata import CaseMetadata
from app.services.embedding_service import EmbeddingService
from app.services.qa_service import QAService
from app.services.file_service import FileService

class CaseService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.qa_service = QAService(db)
        self.file_service = FileService(db)

    # -------------------------
    # Case creation
    # -------------------------
    def _generate_case_no(self, next_id: int):
        now = datetime.datetime.utcnow().strftime("%Y%m%d")
        return f"CASE-{now}-{next_id}"

    def create_case_from_fields(self, case_name: str, description: str | None):
        c = models.case.Case(
            case_name=case_name,
            description=description,
            case_no="temp",
        )
        self.db.add(c)
        self.db.flush()          # get ID
        c.case_no = self._generate_case_no(c.id)
        self.db.commit()
        self.db.refresh(c)
        return c

    # -------------------------
    # File → embeddings → metadata
    # -------------------------
    async def process_file_and_extract_metadata(self, file_id: int) -> dict:
        """
        Orchestrates:
        1. embedding creation
        2. AI metadata extraction
        """
        await self.file_service.process_file_embeddings(file_id)
        return self.qa_service.extract_case_metadata_for_file(file_id)

    # handle_file_upload(...)   ✅ already correct (async)
    # process_file_embeddings(...) ✅ already correct (async)

    # -------------------------
    # Queries
    # -------------------------
    def get_case(self, case_id: int):
        return (
            self.db.query(models.case.Case)
            .filter(models.case.Case.id == case_id)
            .first()
        )

    def list_cases_filtered(
    self,
    skip: int,
    limit: int,
    case_name: Optional[str] = None,
    case_no: Optional[str] = None,
):
        query = (
            self.db.query(Case)
            .options(joinedload(Case.case_metadata))
        )

        if case_name:
            query = query.filter(Case.case_name.ilike(f"%{case_name}%"))

        if case_no:
            query = query.filter(Case.case_no == case_no)

        total = query.count()

        cases = (
            query.order_by(Case.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
    )

        return total, cases

    def save_case_metadata(self, case_id: int, data: dict):
        metadata = CaseMetadata(
            case_id=case_id,
            parties=data.get("parties"),
            court_name=data.get("court_name"),
            filing_date=data.get("filing_date"),
            judge=data.get("judge"),
            attorney=data.get("attorney"),
            next_court_date=data.get("next_court_date"),
            strong_evidence=data.get("strong_evidence"),
            approaching_deadline=data.get("approaching_deadline"),
            case_description=data.get("case_description"),
        )

        self.db.add(metadata)
        self.db.commit()
        self.db.refresh(metadata)
        return metadata
    
    def get_case_with_details(self, case_id: int):
        return (
            self.db.query(Case)
            .options(
                joinedload(Case.case_metadata),  # ✅ FIXED
                joinedload(Case.files),
            )
            .filter(Case.id == case_id)
            .first()
        )