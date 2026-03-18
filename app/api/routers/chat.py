from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.repositories import ArticuloRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ChatService, KeywordRetrievalService

router = APIRouter(tags=["chat"])


def _run_chat(
    payload: ChatRequest,
    db: Session,
    settings: Settings,
) -> ChatResponse:
    top_k = payload.top_k or settings.retrieval_top_k_default
    top_k = min(top_k, settings.retrieval_top_k_max)

    repository = ArticuloRepository(db)
    retrieval = KeywordRetrievalService(repository=repository)
    query_terms, _, retrieval_results = retrieval.search(
        question=payload.question,
        norma_codigo=payload.norma_codigo,
        top_k=top_k,
        candidate_pool=settings.retrieval_candidate_pool,
    )

    if not retrieval_results:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron articulos relevantes en la base.",
        )

    chat_service = ChatService(settings=settings)
    try:
        answer, llm_used = chat_service.answer_question(
            question=payload.question,
            retrieval_results=retrieval_results,
            use_llm=payload.use_llm,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al consultar proveedor LLM: {exc}") from exc

    references = chat_service.build_references(retrieval_results)
    return ChatResponse(
        answer=answer,
        llm_used=llm_used,
        query_terms=query_terms,
        references=references,
    )


@router.post("/chat", response_model=ChatResponse)
def chat_legacy(
    payload: ChatRequest,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> ChatResponse:
    return _run_chat(payload=payload, db=db, settings=settings)


@router.post("/chat/query", response_model=ChatResponse)
def chat_query(
    payload: ChatRequest,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> ChatResponse:
    return _run_chat(payload=payload, db=db, settings=settings)

