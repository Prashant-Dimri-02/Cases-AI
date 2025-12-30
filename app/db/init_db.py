# app/db/init_db.py
from app.db.session import engine
from sqlalchemy import text
from app.db.base import Base
import logging

def init_extensions():
    # Create all tables if not exist
    from app import models  # import to ensure modules define models
    Base.metadata.create_all(bind=engine)
    # Try to create pgvector if available - ignore errors
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            logging.info("pgvector extension created (if supported).")
    except Exception as e:
        logging.info(f"Could not create pgvector extension: {e}")
