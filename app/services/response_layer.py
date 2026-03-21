from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.chat import ClarificationOption, ClarificationPrompt
from app.services.chat import ChatService
from app.services.query_understanding import QueryUnderstandingResult
from app.services.retrieval_layer import EvidenceResult
from app.services.validation_layer import SupportLevel, ValidationDecision, ValidationResult


@dataclass(slots=True)
class GeneratedResponse:
    answer: str
    llm_used: bool
    clarification: ClarificationPrompt | None


class ResponseLayerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat_service = ChatService(settings=settings)

    @staticmethod
    def _excerpt(text: str, limit: int = 220) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:limit]

    def _build_clarification(
        self,
        *,
        understanding: QueryUnderstandingResult,
        validation: ValidationResult,
    ) -> ClarificationPrompt:
        options: list[ClarificationOption] = []

        if not understanding.entities.norma_codigos:
            options.append(
                ClarificationOption(
                    code="norma_objetivo",
                    label="Indica la norma o lineamiento exacto (ej. NOM-009-ZOO-1994).",
                )
            )
        if not understanding.entities.temas:
            options.append(
                ClarificationOption(
                    code="proceso_o_tema",
                    label="Indica el proceso puntual (temperaturas, registros, limpieza, inspeccion, etc.).",
                )
            )

        for candidate in understanding.interpretation_candidates[:3]:
            if len(options) >= 3:
                break
            options.append(
                ClarificationOption(
                    code=candidate.intent.value,
                    label=f"Buscas {candidate.intent.value.replace('_', ' ')}?",
                )
            )

        if len(options) < 2:
            options.append(
                ClarificationOption(
                    code="alcance",
                    label="Aclara si quieres requisito textual, interpretacion o paso operativo.",
                )
            )

        if validation.decision == ValidationDecision.out_of_domain:
            question = (
                "La consulta parece fuera del dominio de normas, calidad e inocuidad. "
                "Quieres reformularla dentro de ese alcance?"
            )
        else:
            question = (
                "Para responder con precision normativa, necesito una aclaracion breve. "
                "Selecciona la opcion que mejor describe tu consulta:"
            )
        return ClarificationPrompt(question=question, options=options[:3])

    def _extractive_answer(
        self,
        *,
        evidences: list[EvidenceResult],
        support_level: SupportLevel,
        assumptions: list[str],
        alternatives: list[str],
    ) -> str:
        if not evidences:
            return (
                "Respuesta breve:\n"
                "No hay evidencia documental suficiente para responder de forma confiable.\n\n"
                "Fundamento:\n"
                "- No se recuperaron fragmentos relevantes en la base actual."
            )

        support_text = {
            SupportLevel.explicit_document_support: "Soporte explicito en documentos recuperados.",
            SupportLevel.reasonable_interpretation: "Interpretacion razonable con evidencia parcial.",
            SupportLevel.insufficient_information: "Informacion insuficiente para una conclusion cerrada.",
        }[support_level]

        summary_lines = []
        for item in evidences[:3]:
            summary_lines.append(
                f"- {item.articulo.norma_codigo} {item.articulo.numeral}: "
                f"{self._excerpt(item.articulo.contenido)}"
            )

        assumption_lines = ""
        if assumptions:
            assumption_lines = "\nSupuesto principal:\n- " + assumptions[0]

        alternative_lines = ""
        if alternatives:
            alternative_lines = "\nPosibles interpretaciones alternas:\n- " + "\n- ".join(alternatives[:2])

        return (
            "Respuesta breve:\n"
            "Con base en los fragmentos recuperados, esta es la interpretacion mas consistente.\n\n"
            "Fundamento:\n"
            f"- {support_text}\n"
            f"{chr(10).join(summary_lines)}"
            f"{assumption_lines}"
            f"{alternative_lines}"
        )

    def generate(
        self,
        *,
        question: str,
        understanding: QueryUnderstandingResult,
        validation: ValidationResult,
        evidences: list[EvidenceResult],
        use_llm: bool,
    ) -> GeneratedResponse:
        if validation.decision in {
            ValidationDecision.out_of_domain,
            ValidationDecision.clarification_needed,
            ValidationDecision.insufficient_evidence,
        }:
            clarification = self._build_clarification(understanding=understanding, validation=validation)
            if validation.decision == ValidationDecision.out_of_domain:
                answer = (
                    "Respuesta breve:\n"
                    "La consulta esta fuera del alcance del asistente (normas, calidad e inocuidad).\n\n"
                    "Fundamento:\n"
                    "- El sistema solo responde sobre cumplimiento normativo y procesos asociados."
                )
            elif validation.decision == ValidationDecision.insufficient_evidence:
                answer = (
                    "Respuesta breve:\n"
                    "No hay evidencia suficiente para confirmar o rechazar cumplimiento.\n\n"
                    "Fundamento:\n"
                    "- Se detecto informacion parcial o de baja relevancia en la recuperacion."
                )
            else:
                answer = (
                    "Respuesta breve:\n"
                    "La consulta es demasiado ambigua para emitir una respuesta normativa confiable.\n\n"
                    "Fundamento:\n"
                    "- Faltan datos clave de norma, tema o alcance operativo."
                )
            return GeneratedResponse(answer=answer, llm_used=False, clarification=clarification)

        llm_answer = ""
        llm_used = False
        if use_llm and evidences:
            llm_answer, llm_used = self.chat_service.answer_question(
                question=question,
                retrieval_results=evidences,
                use_llm=use_llm,
            )

        if llm_used and llm_answer:
            support_text = {
                SupportLevel.explicit_document_support: "Soporte: evidencia explicita en documentos.",
                SupportLevel.reasonable_interpretation: "Soporte: interpretacion razonable con posible ambiguedad.",
                SupportLevel.insufficient_information: "Soporte: evidencia limitada.",
            }[validation.support_level]
            assumption_text = ""
            if validation.decision == ValidationDecision.assumption_answer and understanding.assumptions:
                assumption_text = f"\nSupuesto principal: {understanding.assumptions[0]}"
            alternatives_text = ""
            if validation.decision == ValidationDecision.assumption_answer and validation.alternative_interpretations:
                alternatives_text = (
                    "\nPosibles interpretaciones alternas: "
                    + " | ".join(validation.alternative_interpretations[:2])
                )
            answer = (
                "Respuesta breve:\n"
                f"{llm_answer}\n\n"
                "Fundamento:\n"
                f"- {support_text}{assumption_text}{alternatives_text}"
            )
            return GeneratedResponse(answer=answer, llm_used=True, clarification=None)

        answer = self._extractive_answer(
            evidences=evidences,
            support_level=validation.support_level,
            assumptions=understanding.assumptions,
            alternatives=validation.alternative_interpretations,
        )
        return GeneratedResponse(answer=answer, llm_used=False, clarification=None)
