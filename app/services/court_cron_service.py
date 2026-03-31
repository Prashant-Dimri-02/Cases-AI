from sqlalchemy.orm import Session
from datetime import date
from app.models.case_metadata import CaseMetadata
import logging

logger = logging.getLogger(__name__)


class CourtCronService:
    def __init__(self, db: Session):
        self.db = db

    def move_today_hearings_to_previous(self):
        today = date.today()

        cases = (
            self.db.query(CaseMetadata)
            .filter(CaseMetadata.next_court_date == today)
            .all()
        )
        
        if not cases:
            logger.info("No court hearings today")
            return

        for case in cases:
            case.previous_court_date = case.next_court_date
            case.next_court_date = None

        self.db.commit()
        logger.info(f"Updated {len(cases)} cases for court hearing completion")
