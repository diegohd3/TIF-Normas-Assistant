from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.schemas.chat import ConfidenceLevel, QueryIntent
from app.services.query_understanding import QueryUnderstandingResult
from app.services.retrieval_layer import EvidenceResult


class ValidationDecision(str, Enum):
    direct_answer = "direct_answer"
    assumption_answer = "assumption_answer"
    clarification_needed = "clarification_needed"
    out_of_domain = "out_of_domain"
    insufficient_evidence = "insufficient_evidence"


class SupportLevel(str, Enum):
    explicit_document_support = "explicit_document_support"
    reasonable_interpretation = "reasonable_interpretation"
    insufficient_information = "insufficient_information"


@dataclass(slots=True)
class ValidationResult:
    confidence_score: float
    confidence_level: ConfidenceLevel
    decision: ValidationDecision
    support_level: SupportLevel
    evidence_sufficient: bool
    conflict_detected: bool
    coverage_ratio: float
    reasons: list[str] = field(default_factory=list)
    alternative_interpretations: list[str] = field(default_factory=list)


class ValidationLayerService:
    HIGH_THRESHOLD = 0.75
    MEDIUM_THRESHOLD = 0.50
    MIN_TOP_SCORE = 0.34
    MIN_COVERAGE = 0.18

    POSITIVE_MARKERS = (" debe ", " obligatorio ", " se requiere ", " es requisito ", " debera ")
    NEGATIVE_MARKERS = (" no debe ", " prohibido ", " no se permite ", " no podra ")

    def _coverage_ratio(
        self,
        understanding: QueryUnderstandingResult,
        evidences: list[EvidenceResult],
    ) -> float:
        if not understanding.query_terms:
            return 0.0
        matched = set()
        for evidence in evidences:
            matched.update(evidence.matched_terms)
        return round(min(1.0, len(matched) / max(len(set(understanding.query_terms)), 1)), 4)

    def _detect_conflict(self, evidences: list[EvidenceResult]) -> bool:
        has_positive = False
        has_negative = False
        for evidence in evidences[:5]:
            text = f" {evidence.articulo.contenido.lower()} "
            if any(marker in text for marker in self.POSITIVE_MARKERS):
                has_positive = True
            if any(marker in text for marker in self.NEGATIVE_MARKERS):
                has_negative = True
        return has_positive and has_negative

    def _confidence_level(self, score: float) -> ConfidenceLevel:
        if score >= self.HIGH_THRESHOLD:
            return ConfidenceLevel.high
        if score >= self.MEDIUM_THRESHOLD:
            return ConfidenceLevel.medium
        return ConfidenceLevel.low

    def _alternative_interpretations(self, understanding: QueryUnderstandingResult) -> list[str]:
        alternatives = []
        for candidate in understanding.interpretation_candidates[1:3]:
            alternatives.append(
                f"Podria tratarse de '{candidate.intent.value}' ({candidate.confidence:.2f})."
            )
        return alternatives

    def evaluate(
        self,
        *,
        understanding: QueryUnderstandingResult,
        evidences: list[EvidenceResult],
    ) -> ValidationResult:
        reasons: list[str] = []
        if not understanding.domain_in_scope:
            reasons.append("consulta_fuera_de_dominio")
            return ValidationResult(
                confidence_score=0.05,
                confidence_level=ConfidenceLevel.low,
                decision=ValidationDecision.out_of_domain,
                support_level=SupportLevel.insufficient_information,
                evidence_sufficient=False,
                conflict_detected=False,
                coverage_ratio=0.0,
                reasons=reasons,
                alternative_interpretations=[],
            )

        top_score = evidences[0].score if evidences else 0.0
        avg_top3 = sum(item.score for item in evidences[:3]) / max(min(len(evidences), 3), 1)
        coverage = self._coverage_ratio(understanding, evidences)
        conflict = self._detect_conflict(evidences)

        retrieval_signal = min(1.0, top_score) * 0.45 + min(1.0, avg_top3) * 0.2
        intent_signal = understanding.intent_confidence * 0.15
        coverage_signal = coverage * 0.2
        ambiguity_penalty = understanding.ambiguity_score * 0.2
        conflict_penalty = 0.18 if conflict else 0.0

        confidence = max(
            0.0,
            min(
                1.0,
                retrieval_signal + intent_signal + coverage_signal - ambiguity_penalty - conflict_penalty,
            ),
        )
        confidence = round(confidence, 4)
        level = self._confidence_level(confidence)

        evidence_sufficient = bool(
            evidences
            and top_score >= self.MIN_TOP_SCORE
            and coverage >= self.MIN_COVERAGE
        )

        if not evidences:
            reasons.append("sin_evidencia_recuperada")
        elif top_score < self.MIN_TOP_SCORE:
            reasons.append("evidencia_debil_relevancia")
        if coverage < self.MIN_COVERAGE:
            reasons.append("cobertura_baja_de_terminos")
        if conflict:
            reasons.append("posible_conflicto_entre_fragmentos")
        if understanding.intent == QueryIntent.too_ambiguous:
            reasons.append("consulta_detectada_como_demasiado_ambigua")

        alternatives = self._alternative_interpretations(understanding)
        if level == ConfidenceLevel.high and evidence_sufficient:
            return ValidationResult(
                confidence_score=confidence,
                confidence_level=level,
                decision=ValidationDecision.direct_answer,
                support_level=SupportLevel.explicit_document_support,
                evidence_sufficient=evidence_sufficient,
                conflict_detected=conflict,
                coverage_ratio=coverage,
                reasons=reasons,
                alternative_interpretations=alternatives,
            )

        if level == ConfidenceLevel.medium and evidences:
            support = SupportLevel.reasonable_interpretation
            if not evidence_sufficient:
                support = SupportLevel.insufficient_information
            return ValidationResult(
                confidence_score=confidence,
                confidence_level=level,
                decision=ValidationDecision.assumption_answer,
                support_level=support,
                evidence_sufficient=evidence_sufficient,
                conflict_detected=conflict,
                coverage_ratio=coverage,
                reasons=reasons,
                alternative_interpretations=alternatives,
            )

        decision = (
            ValidationDecision.insufficient_evidence
            if evidences
            else ValidationDecision.clarification_needed
        )
        if understanding.intent == QueryIntent.too_ambiguous:
            decision = ValidationDecision.clarification_needed

        return ValidationResult(
            confidence_score=confidence,
            confidence_level=ConfidenceLevel.low,
            decision=decision,
            support_level=SupportLevel.insufficient_information,
            evidence_sufficient=evidence_sufficient,
            conflict_detected=conflict,
            coverage_ratio=coverage,
            reasons=reasons,
            alternative_interpretations=alternatives,
        )
