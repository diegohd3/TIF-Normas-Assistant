from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend para consulta de normas TIF con FastAPI + PostgreSQL",
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Endpoints legacy y actuales
app.include_router(api_router)

# Alias versionado para evolucionar sin romper clientes existentes
app.include_router(api_router, prefix=settings.api_v1_prefix, include_in_schema=False)

