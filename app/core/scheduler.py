from apscheduler.schedulers.background import BackgroundScheduler
from app.db.session import SessionLocal
from app.services.court_cron_service import CourtCronService
import logging

logger = logging.getLogger(__name__)


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    def daily_court_job():
        db = SessionLocal()
        try:
            service = CourtCronService(db)
            service.move_today_hearings_to_previous()
        finally:
            db.close()
    # ⏰ Runs EVERY DAY at 00:05 AM
    scheduler.add_job(
        daily_court_job,
        trigger="cron",
        hour=0,
        minute=5,
        id="daily_court_date_update",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Court date cron scheduler started")
