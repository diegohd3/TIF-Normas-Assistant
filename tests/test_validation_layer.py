from __future__ import annotations

import unittest

from app.repositories import ArticuloRecord
from app.schemas.chat import QueryIntent
from app.services.query_understanding import QueryEntities, QueryUnderstandingResult
from app.services.retrieval_layer import EvidenceResult
from app.services.validation_layer import ValidationDecision, ValidationLayerService


def _understanding(
    *,
    intent: QueryIntent = QueryIntent.requirement_interpretation,
    ambiguity: float = 0.2,
    domain_in_scope: bool = True,
) -> QueryUnderstandingResult:
    return QueryUnderstandingResult(
        raw_question="¿Es obligatorio registrar temperatura?",
        normalized_question="es obligatorio registrar temperatura",
        corrected_question="es obligatorio registrar temperatura",
        query_terms=["obligatorio", "registrar", "temperatura"],
        expanded_terms=["obligatorio", "registrar", "temperatura", "requisito"],
        entities=QueryEntities(norma_codigos=["NOM-009-ZOO-1994"], numerales=[], temas=["temperatura"]),
        intent=intent,
        intent_confidence=0.82,
        intent_scores={
            QueryIntent.requirement_interpretation: 0.82,
            QueryIntent.operational_compliance: 0.18,
        },
        ambiguity_score=ambiguity,
        ambiguity_signals=[],
        domain_score=0.9,
        domain_in_scope=domain_in_scope,
        interpretation_candidates=[],
        assumptions=[],
    )


def _evidence(score: float = 0.88) -> EvidenceResult:
    articulo = ArticuloRecord(
        id=1,
        norma_codigo="NOM-009-ZOO-1994",
        numeral="5.2",
        nivel=2,
        parent_numeral="5",
        titulo="Control de temperaturas",
        contenido="Se debe registrar la temperatura de refrigeración en cada lote.",
        pagina_inicio=12,
        pagina_fin=12,
    )
    return EvidenceResult(
        articulo=articulo,
        score=score,
        matched_terms=["registrar", "temperatura"],
        lexical_score=8,
        topic_hits=["temperatura"],
    )


class ValidationLayerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ValidationLayerService()

    def test_direct_answer_on_high_confidence(self) -> None:
        result = self.service.evaluate(
            understanding=_understanding(),
            evidences=[_evidence(0.9), _evidence(0.82)],
        )
        self.assertEqual(result.decision, ValidationDecision.direct_answer)
        self.assertGreaterEqual(result.confidence_score, 0.75)

    def test_clarification_when_no_evidence(self) -> None:
        result = self.service.evaluate(
            understanding=_understanding(intent=QueryIntent.too_ambiguous, ambiguity=0.85),
            evidences=[],
        )
        self.assertEqual(result.decision, ValidationDecision.clarification_needed)
        self.assertLess(result.confidence_score, 0.5)

    def test_out_of_domain_rejected(self) -> None:
        result = self.service.evaluate(
            understanding=_understanding(
                intent=QueryIntent.out_of_domain,
                ambiguity=0.1,
                domain_in_scope=False,
            ),
            evidences=[_evidence(0.9)],
        )
        self.assertEqual(result.decision, ValidationDecision.out_of_domain)


if __name__ == "__main__":
    unittest.main()
