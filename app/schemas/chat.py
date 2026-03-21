from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    direct_norm_search = "direct_norm_search"
    requirement_interpretation = "requirement_interpretation"
    criteria_comparison = "criteria_comparison"
    operational_compliance = "operational_compliance"
    out_of_domain = "out_of_domain"
    too_ambiguous = "too_ambiguous"


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    norma_codigo: str | None = Field(
        default=None,
        description="Opcional: limita la consulta a una norma especifica",
    )
    top_k: int | None = Field(default=None, ge=1, le=50)
    use_llm: bool = Field(
        default=True,
        description="Cuando es false solo regresa recuperacion y trazabilidad",
    )
    session_id: str | None = Field(
        default=None,
        description="Identificador de sesion para trazabilidad entre turnos",
    )
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Historial reciente del chat para resolver referencias ambiguas (esto, eso, asi)",
    )


class ChatReference(BaseModel):
    norma_codigo: str
    numeral: str
    titulo: str
    pagina_inicio: int
    pagina_fin: int
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    llm_used: bool
    query_terms: list[str]
    references: list[ChatReference]


class NormativeEntities(BaseModel):
    norma_codigos: list[str] = Field(default_factory=list)
    numerales: list[str] = Field(default_factory=list)
    temas: list[str] = Field(default_factory=list)


class InterpretationCandidate(BaseModel):
    intent: QueryIntent
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ClarificationOption(BaseModel):
    code: str
    label: str


class ClarificationPrompt(BaseModel):
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)


class ChatQueryResponse(ChatResponse):
    response_mode: Literal[
        "direct_answer",
        "assumption_answer",
        "clarification_needed",
        "out_of_domain",
        "insufficient_evidence",
    ]
    support_level: Literal[
        "explicit_document_support",
        "reasonable_interpretation",
        "insufficient_information",
    ]
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    detected_intent: QueryIntent
    intent_confidence: float = Field(ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    ambiguity_signals: list[str] = Field(default_factory=list)
    domain_in_scope: bool = True
    extracted_entities: NormativeEntities = Field(default_factory=NormativeEntities)
    interpretation_candidates: list[InterpretationCandidate] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    alternative_interpretations: list[str] = Field(default_factory=list)
    clarification: ClarificationPrompt | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    trace_id: str

