from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.repositories import ArticuloRepository, NormaRepository
from app.schemas.articulo import ArticuloDetail, ArticuloSummary, SearchHit, SearchResponse
from app.schemas.norma import NormaRead
from app.services import KeywordRetrievalService

router = APIRouter(tags=["normas"])


@router.get("/normas", response_model=list[NormaRead])
def list_normas(db: Session = Depends(get_db_session)) -> list[NormaRead]:
    repository = NormaRepository(db)
    rows = repository.list_normas()
    return [
        NormaRead(
            codigo=row.codigo,
            titulo=row.titulo,
            archivo_origen=row.archivo_origen,
            total_articulos=row.total_articulos,
        )
        for row in rows
    ]


@router.get("/articulos", response_model=list[ArticuloSummary])
def list_articulos(
    norma_codigo: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> list[ArticuloSummary]:
    repository = ArticuloRepository(db)
    rows = repository.list_articulos(
        norma_codigo=norma_codigo,
        limit=limit,
        offset=offset,
    )
    return [
        ArticuloSummary(
            id=row.id,
            norma_codigo=row.norma_codigo,
            numeral=row.numeral,
            nivel=row.nivel,
            parent_numeral=row.parent_numeral,
            titulo=row.titulo,
            pagina_inicio=row.pagina_inicio,
            pagina_fin=row.pagina_fin,
        )
        for row in rows
    ]


@router.get("/articulos/{norma_codigo}/{numeral}", response_model=ArticuloDetail)
def get_articulo(
    norma_codigo: str,
    numeral: str,
    db: Session = Depends(get_db_session),
) -> ArticuloDetail:
    repository = ArticuloRepository(db)
    row = repository.get_articulo(norma_codigo=norma_codigo, numeral=numeral)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontro articulo {numeral} en {norma_codigo}",
        )
    return ArticuloDetail(
        id=row.id,
        norma_codigo=row.norma_codigo,
        numeral=row.numeral,
        nivel=row.nivel,
        parent_numeral=row.parent_numeral,
        titulo=row.titulo,
        contenido=row.contenido,
        pagina_inicio=row.pagina_inicio,
        pagina_fin=row.pagina_fin,
    )


@router.get("/articulos/search", response_model=SearchResponse)
def search_articulos(
    q: str = Query(..., min_length=3, description="Consulta por palabras clave"),
    norma_codigo: str | None = Query(default=None),
    top_k: int | None = Query(default=None, ge=1, le=50),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> SearchResponse:
    requested_top_k = top_k or settings.retrieval_top_k_default
    requested_top_k = min(requested_top_k, settings.retrieval_top_k_max)

    repository = ArticuloRepository(db)
    retrieval = KeywordRetrievalService(repository=repository)
    query_terms, candidate_count, results = retrieval.search(
        question=q,
        norma_codigo=norma_codigo,
        top_k=requested_top_k,
        candidate_pool=settings.retrieval_candidate_pool,
    )

    return SearchResponse(
        query=q,
        norma_codigo=norma_codigo,
        top_k=requested_top_k,
        query_terms=query_terms,
        candidate_count=candidate_count,
        results=[
            SearchHit(
                id=result.articulo.id,
                norma_codigo=result.articulo.norma_codigo,
                numeral=result.articulo.numeral,
                nivel=result.articulo.nivel,
                parent_numeral=result.articulo.parent_numeral,
                titulo=result.articulo.titulo,
                contenido=result.articulo.contenido,
                pagina_inicio=result.articulo.pagina_inicio,
                pagina_fin=result.articulo.pagina_fin,
                score=float(result.score),
                matched_terms=result.matched_terms,
            )
            for result in results
        ],
    )
