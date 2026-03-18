from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"], include_in_schema=False)

UI_FILE = Path(__file__).resolve().parents[2] / "web" / "dummy.html"


@router.get("/ui")
def dummy_ui() -> FileResponse:
    if not UI_FILE.exists():
        raise HTTPException(status_code=500, detail="No se encontro la interfaz dummy.")
    return FileResponse(UI_FILE, media_type="text/html")

