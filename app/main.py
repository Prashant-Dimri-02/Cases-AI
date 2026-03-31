from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.api_router import api_router
from app.core.config import settings
from app.db import init_db
import logging
from app.core.logging import configure_logging
import os
from app.core.scheduler import start_scheduler

configure_logging()

app = FastAPI(title="Case AI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔥 dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def startup_event():
    logging.info("Starting up: initializing DB...")

    # ✅ DB must be ready BEFORE scheduler starts
    init_db.init_extensions()

    logging.info("DB initialized. Starting scheduler...")

    # ✅ Safe to start cron now
    start_scheduler()

    logging.info("Startup complete")
