# app/core/config.py

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    # ===============================
    # APP
    # ===============================
    PROJECT_NAME: str = "Case AI Backend"
    DEBUG: bool = True
    ENV: str = "development"

    # ===============================
    # DATABASE
    # ===============================
    DATABASE_URL: str  # MUST come from .env

    # ===============================
    # FILE UPLOADS
    # ===============================
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")

    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # fallback
    ALLOWED_UPLOAD_TYPES: str = "application/pdf"

    # ===============================
    # JWT / AUTH
    # ===============================
    JWT_SECRET: str  # MUST come from .env
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ===============================
    # OPENAI / AI
    # ===============================
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ===============================
    # OPTIONAL STORAGE (AWS / Azure later)
    # ===============================
    S3_BUCKET: Optional[str] = None
    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()
