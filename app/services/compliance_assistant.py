from __future__ import annotations

from uuid import uuid4

from app.core.config import Settings
from app.repositories import ArticuloRepository
from app.schemas.chat import (
    ChatQueryResponse,
    ChatRequest,
    InterpretationCandidate,
    NormativeEntities,
    QueryIntent,
)
from app.services.observability import ObservabilityService
from app.services.query_understanding import QueryUnderstandingService
from app.services.response_layer import ResponseLayerService
from app.services.retrieval_layer import RetrievalLayerService
from app.services.validation_layer import ValidationLayerService


class ComplianceAssistantService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: ArticuloRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.query_understanding = QueryUnderstandingService()
        self.retrieval_layer = RetrievalLayerService(repository=repository)
        self.validation_layer = ValidationLayerService()
        self.response_layer = ResponseLayerService(settings=settings)
        self.observability = ObservabilityService()

    def answer(self, payload: ChatRequest) -> ChatQueryResponse:
        trace_id = payload.session_id or str(uuid4())
        history_messages = [turn.content for turn in payload.history]

        understanding = self.query_understanding.analyze(
            question=payload.question,
            history_messages=history_messages,
        )
        if payload.norma_codigo and payload.norma_codigo not in understanding.entities.norma_codigos:
            understanding.entities.norma_codigos.insert(0, payload.norma_codigo)
            understanding.assumptions.append(
                f"Se aplica filtro explicito a la norma {payload.norma_codigo} enviado por el usuario."
            )

        top_k = payload.top_k or self.settings.retrieval_top_k_default
        top_k = min(top_k, self.settings.retrieval_top_k_max)
        query_terms: list[str] = []
        candidate_count = 0
        evidences = []
        if understanding.domain_in_scope:
            query_terms, candidate_count, evidences = self.retrieval_layer.retrieve(
                understanding=understanding,
                norma_codigo=payload.norma_codigo,
                top_k=top_k,
                candidate_pool=self.settings.retrieval_candidate_pool,
            )

        validation = self.validation_layer.evaluate(
            understanding=understanding,
            evidences=evidences,
        )

        generated = self.response_layer.generate(
            question=payload.question,
            understanding=understanding,
            validation=validation,
            evidences=evidences,
            use_llm=payload.use_llm,
        )

        references = self.response_layer.chat_service.build_references(evidences)
        interpretations = [
            InterpretationCandidate(
                intent=item.intent,
                confidence=item.confidence,
                rationale=item.rationale,
            )
            for item in understanding.interpretation_candidates
        ]

        if understanding.intent == QueryIntent.out_of_domain:
            query_terms = []
            references = []

        self.observability.log_event(
            trace_id=trace_id,
            event="query_understanding",
            payload={
                "intent": understanding.intent.value,
                "intent_confidence": understanding.intent_confidence,
                "ambiguity_score": understanding.ambiguity_score,
                "ambiguity_signals": understanding.ambiguity_signals,
                "domain_in_scope": understanding.domain_in_scope,
                "query_terms": understanding.query_terms,
                "entities": {
                    "norma_codigos": understanding.entities.norma_codigos,
                    "numerales": understanding.entities.numerales,
                    "temas": understanding.entities.temas,
                },
            },
        )

        self.observability.log_event(
            trace_id=trace_id,
            event="retrieval",
            payload={
                "query_terms": query_terms,
                "candidate_count": candidate_count,
                "top_evidence": [
                    {
                        "norma_codigo": item.articulo.norma_codigo,
                        "numeral": item.articulo.numeral,
                        "score": item.score,
                        "matched_terms": item.matched_terms[:8],
                    }
                    for item in evidences[:5]
                ],
            },
        )

        self.observability.log_event(
            trace_id=trace_id,
            event="validation",
            payload={
                "decision": validation.decision.value,
                "support_level": validation.support_level.value,
                "confidence_score": validation.confidence_score,
                "confidence_level": validation.confidence_level.value,
                "coverage_ratio": validation.coverage_ratio,
                "conflict_detected": validation.conflict_detected,
                "reasons": validation.reasons,
            },
        )

        return ChatQueryResponse(
            answer=generated.answer,
            llm_used=generated.llm_used,
            query_terms=query_terms,
            references=references,
            response_mode=validation.decision.value,
            support_level=validation.support_level.value,
            confidence_score=validation.confidence_score,
            confidence_level=validation.confidence_level,
            detected_intent=understanding.intent,
            intent_confidence=understanding.intent_confidence,
            ambiguity_score=understanding.ambiguity_score,
            ambiguity_signals=understanding.ambiguity_signals,
            domain_in_scope=understanding.domain_in_scope,
            extracted_entities=NormativeEntities(
                norma_codigos=understanding.entities.norma_codigos,
                numerales=understanding.entities.numerales,
                temas=understanding.entities.temas,
            ),
            interpretation_candidates=interpretations,
            assumptions=understanding.assumptions,
            alternative_interpretations=validation.alternative_interpretations,
            clarification=generated.clarification,
            decision_reasons=validation.reasons,
            trace_id=trace_id,
        )
