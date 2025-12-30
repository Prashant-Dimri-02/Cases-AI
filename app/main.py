# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.api_router import api_router
from app.core.config import settings
from app.db import init_db
import logging
from app.core.logging import configure_logging
import os

configure_logging()

app = FastAPI(title="Case AI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔥 for development (ngrok / localhost / frontend)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
# mount
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

app.include_router(api_router, prefix="/api")

@app.on_event("startup")
def on_startup():
    logging.info("Starting up: initializing DB...")
    init_db.init_extensions()  # create pgvector extension or any DB init tasks
    logging.info("Startup complete")
