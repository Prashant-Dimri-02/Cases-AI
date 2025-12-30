# app/services/case_service.py
from sqlalchemy.orm import Session
from app import models
from app.schemas.case import CaseCreate
from sqlalchemy.exc import IntegrityError
import datetime
from app.models.case import Case

class CaseService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_case_no(self, next_id: int):
        now = datetime.datetime.utcnow().strftime("%Y%m%d")
        return f"CASE-{now}-{next_id}"

    def create_case(self, payload: CaseCreate):
        # create case, generate case_no after flush to get id
        c = models.case.Case(case_name=payload.case_name, description=payload.description, case_no="temp")
        self.db.add(c)
        self.db.flush()  # get id
        c.case_no = self._generate_case_no(c.id)
        self.db.commit()
        self.db.refresh(c)
        return c

    def get_case(self, case_id: int):
        return self.db.query(models.case.Case).filter(models.case.Case.id == case_id).first()

    def list_cases(self, skip: int = 0, limit: int = 20):
        return (
            self.db.query(Case)
            .order_by(Case.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )