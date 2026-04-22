# app/services/case_service.py

from typing import Optional
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from app import models
from app.models.case import Case
from app.models.case_metadata import CaseMetadata
from app.services.embedding_service import EmbeddingService
from app.services.qa_service import QAService
from app.services.file_service import FileService
from app.models.case_file import FileStatus


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
        now = datetime.utcnow().strftime("%Y%m%d")
        return f"CASE-{now}-{next_id}"

    def create_case_from_fields(self, case_name: str, description: Optional[str], owner_id: int):
        case = Case(
            case_name=case_name,
            description=description,
            case_no="temp",
            owner_id=owner_id,
        )
        self.db.add(case)
        self.db.flush()

        case.case_no = self._generate_case_no(case.id)

        self.db.commit()
        self.db.refresh(case)

        return case

    # -------------------------
    # Queries
    # -------------------------
    def get_case(self, case_id: int):
        return (
            self.db.query(Case)
            .filter(Case.id == case_id)
            .first()
        )

    def get_case_with_details(self, case_id: int):
        return (
            self.db.query(Case)
            .options(
                joinedload(Case.case_metadata),
                joinedload(Case.files),
            )
            .filter(Case.id == case_id)
            .first()
        )

    def list_cases_filtered(
        self,
        skip: int,
        limit: int,
        case_name: Optional[str] = None,
        case_no: Optional[str] = None,
        user=None,
    ):
        query = self.db.query(Case).options(
            joinedload(Case.case_metadata)
        )

        # -------------------------
        # RBAC FILTERING
        # -------------------------
        if user:
            user_roles = [r.name for r in user.roles]

            if "ADMIN" in user_roles:
                pass

            elif "MANAGER" in user_roles:
                query = query.filter(Case.owner_id == user.id)

            else:
                query = query.filter(
                    Case.users.any(models.user.User.id == user.id)
                )

        # -------------------------
        # Filters
        # -------------------------
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

    # -------------------------
    # Metadata Handling
    # -------------------------
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
            previous_court_date=data.get("previous_court_date"),
        )

        self.db.add(metadata)
        self.db.commit()
        self.db.refresh(metadata)

        return metadata

    # -------------------------
    # FILE PROCESSING (NEW FLOW)
    # -------------------------
    async def process_file_and_extract_metadata(self, file_id: int) -> dict:
        """
        Process file ONLY if approved (file-level).
        """

        file_model = self.file_service.get_file_by_id(file_id)

        if not file_model:
            raise ValueError("File not found")

        # ✅ Check file-level approval
        if file_model.status != FileStatus.APPROVED:
            return {
                "processed": False,
                "message": "File not approved by admin"
            }

        # ✅ Process embeddings (safe)
        result = await self.file_service.process_file_embeddings_safe(file_id)

        # ✅ Extract metadata AFTER processing
        extracted_metadata = self.qa_service.extract_case_metadata_for_file(file_id)

        if extracted_metadata:
            self.qa_service.merge_case_metadata_for_case(
                file_model.case_id,
                extracted_metadata
            )

        return {
            "processed": True,
            "metadata": extracted_metadata
        }