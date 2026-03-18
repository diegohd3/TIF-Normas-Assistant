from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def get_app_settings() -> Settings:
    return get_settings()

