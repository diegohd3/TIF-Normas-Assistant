from __future__ import annotations

from typing import Sequence

from openai import OpenAI

from app.core.config import Settings
from app.schemas.chat import ChatReference
from app.services.retrieval import RetrievalResult


SYSTEM_PROMPT = """Eres TIF Normas Assistant.
Responde solo con la informacion provista en el contexto de articulos de normas.
Si no hay evidencia suficiente, dilo claramente.
No inventes numerales ni texto normativo.
Incluye al final una seccion breve llamada Referencias con numerales citados.
Responde en espanol.
"""


class ChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _excerpt(text: str, limit: int = 260) -> str:
        clean = " ".join(text.split())
        return clean[:limit]

    def build_context(self, retrieval_results: Sequence[RetrievalResult]) -> str:
        blocks: list[str] = []
        for result in retrieval_results:
            articulo = result.articulo
            content = articulo.contenido[: self.settings.retrieval_snippet_chars]
            blocks.append(
                (
                    f"[{articulo.norma_codigo} {articulo.numeral}] {articulo.titulo} "
                    f"(paginas {articulo.pagina_inicio}-{articulo.pagina_fin})\n"
                    f"{content}"
                )
            )
        return "\n\n---\n\n".join(blocks)

    def build_references(self, retrieval_results: Sequence[RetrievalResult]) -> list[ChatReference]:
        return [
            ChatReference(
                norma_codigo=result.articulo.norma_codigo,
                numeral=result.articulo.numeral,
                titulo=result.articulo.titulo,
                pagina_inicio=result.articulo.pagina_inicio,
                pagina_fin=result.articulo.pagina_fin,
                score=float(result.score),
                excerpt=self._excerpt(result.articulo.contenido),
            )
            for result in retrieval_results
        ]

    def _fallback_answer(self, retrieval_results: Sequence[RetrievalResult]) -> str:
        if not retrieval_results:
            return "No se encontro evidencia en la base para responder la pregunta."

        lines = ["Resumen extractivo de articulos recuperados:"]
        for result in retrieval_results[:3]:
            articulo = result.articulo
            lines.append(
                f"- {articulo.norma_codigo} {articulo.numeral}: {self._excerpt(articulo.contenido, limit=180)}"
            )
        lines.append("Nota: configura OPENAI_API_KEY para generar respuesta redactada con LLM.")
        return "\n".join(lines)

    def answer_question(
        self,
        question: str,
        retrieval_results: Sequence[RetrievalResult],
        use_llm: bool,
    ) -> tuple[str, bool]:
        context = self.build_context(retrieval_results)
        if not use_llm:
            return self._fallback_answer(retrieval_results), False

        if not self.settings.openai_api_key:
            return self._fallback_answer(retrieval_results), False

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )

        user_prompt = (
            "Pregunta del usuario:\n"
            f"{question}\n\n"
            "Contexto normativo relevante:\n"
            f"{context}\n\n"
            "Instrucciones:\n"
            "- Responde de forma clara y concreta.\n"
            "- Cita numerales en formato NOM-XXX numeral.\n"
            "- Si falta evidencia, indicalo.\n"
        )

        response = client.responses.create(
            model=self.settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            temperature=0.1,
        )
        return response.output_text.strip(), True

