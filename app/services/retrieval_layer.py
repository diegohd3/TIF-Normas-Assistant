from __future__ import annotations

from dataclasses import dataclass

from app.repositories import ArticuloRecord, ArticuloRepository
from app.services.query_understanding import QueryUnderstandingResult
from app.services.retrieval import KeywordRetrievalService, RetrievalResult


TOPIC_KEYWORDS = {
    "temperatura": {"temperatura", "temperaturas", "refrigeracion", "congelacion", "termico"},
    "registros": {"registro", "registros", "bitacora", "evidencia", "formato"},
    "limpieza": {"limpieza", "higiene", "sanitizacion", "desinfeccion"},
    "inspeccion": {"inspeccion", "ante mortem", "post mortem", "dictamen"},
    "trazabilidad": {"trazabilidad", "lote", "etiquetado"},
}


@dataclass(slots=True)
class EvidenceResult:
    articulo: ArticuloRecord
    score: float
    matched_terms: list[str]
    lexical_score: int
    topic_hits: list[str]


class RetrievalLayerService:
    def __init__(self, repository: ArticuloRepository) -> None:
        self.repository = repository
        self.keyword = KeywordRetrievalService(repository=repository)

    def _topic_hits(self, contenido: str, temas: list[str]) -> list[str]:
        haystack = contenido.lower()
        hits = []
        for topic in temas:
            keywords = TOPIC_KEYWORDS.get(topic, {topic})
            if any(keyword in haystack for keyword in keywords):
                hits.append(topic)
        return hits

    def _rerank_score(
        self,
        *,
        articulo: ArticuloRecord,
        lexical_score: int,
        matched_terms: list[str],
        understanding: QueryUnderstandingResult,
        norma_filter: str | None,
        topic_hits: list[str],
    ) -> float:
        base = min(1.0, lexical_score / 9.0) * 0.55
        terms_coverage = 0.0
        if understanding.query_terms:
            terms_coverage = min(1.0, len(set(matched_terms)) / max(len(set(understanding.query_terms)), 1))
        coverage_signal = terms_coverage * 0.2

        norm_boost = 0.0
        preferred_norms = set(understanding.entities.norma_codigos)
        if norma_filter and articulo.norma_codigo == norma_filter:
            norm_boost += 0.15
        elif preferred_norms and articulo.norma_codigo in preferred_norms:
            norm_boost += 0.1

        numeral_boost = 0.0
        if understanding.entities.numerales and articulo.numeral in understanding.entities.numerales:
            numeral_boost += 0.08

        topic_boost = min(0.12, 0.04 * len(topic_hits))
        final_score = base + coverage_signal + norm_boost + numeral_boost + topic_boost
        return round(min(1.0, final_score), 4)

    def retrieve(
        self,
        *,
        understanding: QueryUnderstandingResult,
        norma_codigo: str | None,
        top_k: int,
        candidate_pool: int,
    ) -> tuple[list[str], int, list[EvidenceResult]]:
        query_terms = understanding.expanded_terms[:14]
        search_text = " ".join(query_terms) if query_terms else understanding.corrected_question

        _, candidate_count, lexical_results = self.keyword.search(
            question=search_text,
            norma_codigo=norma_codigo,
            top_k=max(candidate_pool, top_k),
            candidate_pool=max(candidate_pool, top_k),
        )

        if not lexical_results and (norma_codigo or understanding.entities.norma_codigos):
            fallback_norma = norma_codigo or understanding.entities.norma_codigos[0]
            candidates = self.repository.list_articulos(
                norma_codigo=fallback_norma,
                limit=max(top_k, 8),
                offset=0,
            )
            lexical_results = self.keyword.search(
                question=search_text,
                norma_codigo=fallback_norma,
                top_k=max(top_k, 8),
                candidate_pool=max(top_k, 8),
            )[2]
            if not lexical_results:
                lexical_results = [RetrievalResult(articulo=row, score=0, matched_terms=[]) for row in candidates]

        ranked: list[EvidenceResult] = []
        for result in lexical_results:
            topic_hits = self._topic_hits(result.articulo.contenido, understanding.entities.temas)
            score = self._rerank_score(
                articulo=result.articulo,
                lexical_score=int(result.score),
                matched_terms=result.matched_terms,
                understanding=understanding,
                norma_filter=norma_codigo,
                topic_hits=topic_hits,
            )
            ranked.append(
                EvidenceResult(
                    articulo=result.articulo,
                    score=score,
                    matched_terms=result.matched_terms,
                    lexical_score=int(result.score),
                    topic_hits=topic_hits,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.score,
                -item.lexical_score,
                item.articulo.nivel,
                item.articulo.numeral,
            )
        )
        return query_terms, candidate_count, ranked[:top_k]
