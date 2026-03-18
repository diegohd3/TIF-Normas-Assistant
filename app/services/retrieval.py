from __future__ import annotations

import re
from dataclasses import dataclass

from app.repositories import ArticuloRecord, ArticuloRepository


SPANISH_STOPWORDS = {
    "que",
    "para",
    "con",
    "por",
    "del",
    "las",
    "los",
    "una",
    "uno",
    "unos",
    "unas",
    "como",
    "donde",
    "sobre",
    "norma",
    "normas",
    "articulo",
    "articulos",
    "segun",
    "según",
    "esta",
    "este",
    "estos",
    "estas",
    "cual",
    "cuales",
    "cuál",
    "cuáles",
    "puede",
    "pueden",
    "debe",
    "deben",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9áéíóúÁÉÍÓÚñÑüÜ]+")


@dataclass(slots=True)
class RetrievalResult:
    articulo: ArticuloRecord
    score: int
    matched_terms: list[str]


class KeywordRetrievalService:
    def __init__(self, repository: ArticuloRepository) -> None:
        self.repository = repository

    @staticmethod
    def tokenize(text: str) -> list[str]:
        tokens = TOKEN_RE.findall(text.lower())
        return [token for token in tokens if len(token) >= 3 and token not in SPANISH_STOPWORDS]

    @staticmethod
    def _score(articulo: ArticuloRecord, terms: list[str]) -> tuple[int, list[str]]:
        haystack = f"{articulo.titulo} {articulo.contenido}".lower()
        matched = [term for term in terms if term in haystack]
        score = sum(haystack.count(term) for term in terms)
        return score, matched

    def search(
        self,
        question: str,
        norma_codigo: str | None,
        top_k: int,
        candidate_pool: int,
    ) -> tuple[list[str], int, list[RetrievalResult]]:
        terms = self.tokenize(question)[:10]
        pool_limit = max(candidate_pool, top_k)
        candidates = self.repository.search_candidates(
            terms=terms,
            norma_codigo=norma_codigo,
            limit=pool_limit,
        )

        if not candidates and norma_codigo:
            candidates = self.repository.list_articulos(
                norma_codigo=norma_codigo,
                limit=max(top_k, 8),
                offset=0,
            )

        if not terms:
            plain_results = [RetrievalResult(articulo=item, score=0, matched_terms=[]) for item in candidates]
            return terms, len(candidates), plain_results[:top_k]

        ranked = []
        for candidate in candidates:
            score, matched_terms = self._score(candidate, terms)
            ranked.append(
                RetrievalResult(
                    articulo=candidate,
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.score,
                item.articulo.nivel,
                item.articulo.numeral,
            )
        )
        return terms, len(candidates), ranked[:top_k]
