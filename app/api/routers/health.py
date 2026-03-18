from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_app_settings),
    db: Session = Depends(get_db_session),
) -> HealthResponse:
    database_status = "ok"
    try:
        db.execute(sa.text("SELECT 1"))
    except Exception:
        database_status = "error"

    status = "ok" if database_status == "ok" else "degraded"
    return HealthResponse(
        status=status,
        app=settings.app_name,
        env=settings.app_env,
        database=database_status,
    )

