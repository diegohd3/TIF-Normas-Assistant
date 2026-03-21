from __future__ import annotations

import unittest

from app.schemas.chat import QueryIntent
from app.services.query_understanding import QueryUnderstandingService


class QueryUnderstandingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QueryUnderstandingService()

    def test_marks_short_deictic_question_as_too_ambiguous(self) -> None:
        result = self.service.analyze(question="¿esto sí cumple?")
        self.assertEqual(result.intent, QueryIntent.too_ambiguous)
        self.assertGreaterEqual(result.ambiguity_score, 0.65)
        self.assertFalse(result.entities.norma_codigos)

    def test_uses_history_to_infer_missing_context(self) -> None:
        result = self.service.analyze(
            question="¿esto sí cumple?",
            history_messages=[
                "En la NOM-009-ZOO-1994, ¿qué dice de temperaturas de refrigeración?",
                "Aplica control de temperatura y registros en inspección.",
            ],
        )
        self.assertIn("NOM-009-ZOO-1994", result.entities.norma_codigos)
        self.assertTrue(result.assumptions)
        self.assertTrue(result.domain_in_scope)


if __name__ == "__main__":
    unittest.main()
