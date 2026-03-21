from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.schemas.chat import QueryIntent


TOKEN_RE = re.compile(r"[a-z0-9]+")
NORMA_RE = re.compile(r"\b(?:nom|nmx)[-\s]?\d{2,4}(?:[-\s][a-z]{2,8})?[-\s]?\d{4}\b", re.IGNORECASE)
NUMERAL_RE = re.compile(r"\b\d+(?:\.\d+){0,4}\b")

STOPWORDS = {
    "que",
    "como",
    "cual",
    "cuales",
    "donde",
    "cuando",
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
    "sobre",
    "segun",
    "esta",
    "este",
    "estos",
    "estas",
    "eso",
    "esto",
    "asi",
    "hay",
    "debe",
    "deben",
    "puede",
    "pueden",
}

DOMAIN_KEYWORDS = {
    "inocuidad",
    "calidad",
    "norma",
    "normativo",
    "cumplimiento",
    "requisito",
    "auditoria",
    "documental",
    "procedimiento",
    "registro",
    "control",
    "planta",
    "proceso",
    "haccp",
    "temperatura",
    "sanitizacion",
    "desinfeccion",
    "inspeccion",
    "trazabilidad",
    "tif",
    "nom",
    "nmx",
    "alimento",
    "alimentos",
}

TOPIC_HINTS = {
    "temperatura": {"temperatura", "temperaturas", "frio", "calor", "refrigeracion", "congelacion"},
    "registros": {"registro", "registros", "bitacora", "evidencia", "formato"},
    "limpieza": {"limpieza", "sanitizacion", "desinfeccion", "higiene"},
    "inspeccion": {"inspeccion", "inspeccionar", "ante", "post", "mortem"},
    "trazabilidad": {"trazabilidad", "lote", "etiquetado"},
}

TERM_EXPANSIONS = {
    "cumple": ["cumplimiento", "conforme", "requisito"],
    "obligatorio": ["debe", "requisito", "obligacion"],
    "registrarlo": ["registro", "bitacora", "evidencia"],
    "temperaturas": ["temperatura", "refrigeracion", "congelacion", "limite"],
    "norma": ["nom", "nmx", "lineamiento", "criterio"],
    "maneja": ["procedimiento", "operacion", "control"],
}

COMMON_MISSPELLINGS = {
    "temeperatura": "temperatura",
    "tempratura": "temperatura",
    "regstro": "registro",
    "obligatorioo": "obligatorio",
    "cumplimeinto": "cumplimiento",
    "normativdad": "normatividad",
    "inocudad": "inocuidad",
    "audotoria": "auditoria",
    "procedimeinto": "procedimiento",
}

AMBIGUOUS_PATTERNS = (
    "esto si cumple",
    "eso si cumple",
    "como debe ir",
    "que pide la norma",
    "eso se puede o no",
    "como se maneja",
    "que dice de temperaturas",
    "hay que registrarlo",
    "esto es obligatorio",
)

DEICTIC_TOKENS = {"esto", "eso", "asi", "aqui", "ahi", "ello", "esta", "este"}


@dataclass(slots=True)
class QueryEntities:
    norma_codigos: list[str] = field(default_factory=list)
    numerales: list[str] = field(default_factory=list)
    temas: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QueryInterpretation:
    intent: QueryIntent
    confidence: float
    rationale: str


@dataclass(slots=True)
class QueryUnderstandingResult:
    raw_question: str
    normalized_question: str
    corrected_question: str
    query_terms: list[str]
    expanded_terms: list[str]
    entities: QueryEntities
    intent: QueryIntent
    intent_confidence: float
    intent_scores: dict[QueryIntent, float]
    ambiguity_score: float
    ambiguity_signals: list[str]
    domain_score: float
    domain_in_scope: bool
    interpretation_candidates: list[QueryInterpretation]
    assumptions: list[str]


class QueryUnderstandingService:
    def _strip_accents(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def normalize_text(self, text: str) -> str:
        clean = self._strip_accents(text.lower())
        clean = re.sub(r"[^a-z0-9\-\s]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def correct_text(self, text: str) -> str:
        tokens = TOKEN_RE.findall(text)
        corrected = [COMMON_MISSPELLINGS.get(token, token) for token in tokens]
        return " ".join(corrected)

    def tokenize(self, text: str) -> list[str]:
        tokens = TOKEN_RE.findall(text.lower())
        return [token for token in tokens if len(token) >= 3 and token not in STOPWORDS]

    def expand_terms(self, terms: list[str]) -> list[str]:
        expanded = list(terms)
        seen = set(expanded)
        for term in terms:
            for alias in TERM_EXPANSIONS.get(term, []):
                if alias not in seen:
                    expanded.append(alias)
                    seen.add(alias)
        return expanded

    def extract_norma_codes(self, text: str) -> list[str]:
        found = []
        seen = set()
        for match in NORMA_RE.findall(text):
            canonical = re.sub(r"[\s]+", "-", match.upper())
            canonical = re.sub(r"-{2,}", "-", canonical)
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
        return found

    def extract_topics(self, terms: list[str]) -> list[str]:
        topics = []
        terms_set = set(terms)
        for topic, hints in TOPIC_HINTS.items():
            if terms_set.intersection(hints):
                topics.append(topic)
        return topics

    def _domain_score(self, terms: list[str], has_norm_code: bool) -> float:
        if has_norm_code:
            return 0.95
        if not terms:
            return 0.0
        matches = sum(1 for term in terms if term in DOMAIN_KEYWORDS)
        ratio = matches / max(len(terms), 1)
        return min(1.0, ratio * 1.8)

    def _intent_scores(
        self,
        text: str,
        terms: list[str],
        entities: QueryEntities,
    ) -> dict[QueryIntent, float]:
        joined = f" {text} "
        score_map: dict[QueryIntent, float] = {
            QueryIntent.direct_norm_search: 0.0,
            QueryIntent.requirement_interpretation: 0.0,
            QueryIntent.criteria_comparison: 0.0,
            QueryIntent.operational_compliance: 0.0,
        }

        direct_markers = ("que dice", "que pide", "numeral", "articulo", "texto", "norma")
        if any(marker in joined for marker in direct_markers):
            score_map[QueryIntent.direct_norm_search] += 0.45
        if entities.norma_codigos:
            score_map[QueryIntent.direct_norm_search] += 0.25

        interpretation_markers = ("cumple", "obligatorio", "debe", "se puede", "permitido", "prohibido")
        if any(marker in joined for marker in interpretation_markers):
            score_map[QueryIntent.requirement_interpretation] += 0.5

        comparison_markers = (" vs ", " versus ", "compar", "diferencia", "diferencias", "entre ")
        if any(marker in joined for marker in comparison_markers):
            score_map[QueryIntent.criteria_comparison] += 0.75

        operational_markers = ("procedimiento", "operacion", "maneja", "manejo", "registro", "bitacora")
        if any(marker in joined for marker in operational_markers):
            score_map[QueryIntent.operational_compliance] += 0.5

        if "temperatura" in terms or "temperaturas" in terms:
            score_map[QueryIntent.operational_compliance] += 0.15
            score_map[QueryIntent.requirement_interpretation] += 0.10

        if entities.temas:
            score_map[QueryIntent.operational_compliance] += 0.1

        total = sum(score_map.values())
        if total <= 0:
            return score_map

        normalized = {
            intent: round(value / total, 4)
            for intent, value in score_map.items()
        }
        return normalized

    def _ambiguity(
        self,
        text: str,
        terms: list[str],
        entities: QueryEntities,
        inferred_context: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        signals: list[str] = []
        raw_tokens = TOKEN_RE.findall(text)
        if len(terms) <= 3:
            score += 0.25
            signals.append("consulta_muy_corta")

        if any(token in DEICTIC_TOKENS for token in raw_tokens):
            score += 0.2
            signals.append("referencia_deictica")

        if any(pattern in text for pattern in AMBIGUOUS_PATTERNS):
            score += 0.35
            signals.append("patron_ambiguo_frecuente")

        if not entities.norma_codigos and not entities.temas:
            score += 0.25
            signals.append("sin_norma_ni_tema_explicito")

        if inferred_context:
            score = max(0.0, score - 0.2)
            signals.append("contexto_inferido_desde_historial")

        return min(1.0, round(score, 4)), signals

    def _infer_entities_from_history(self, history: list[str]) -> QueryEntities:
        norm_codes: list[str] = []
        numerales: list[str] = []
        topics: list[str] = []
        for item in reversed(history[-6:]):
            normalized = self.normalize_text(item)
            terms = self.tokenize(normalized)
            for code in self.extract_norma_codes(normalized):
                if code not in norm_codes:
                    norm_codes.append(code)
            for numeral in NUMERAL_RE.findall(normalized):
                if numeral not in numerales:
                    numerales.append(numeral)
            for topic in self.extract_topics(terms):
                if topic not in topics:
                    topics.append(topic)
            if norm_codes and topics:
                break
        return QueryEntities(norma_codigos=norm_codes, numerales=numerales, temas=topics)

    def _build_interpretations(
        self,
        scores: dict[QueryIntent, float],
    ) -> list[QueryInterpretation]:
        sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top = []
        rationales = {
            QueryIntent.direct_norm_search: "Consulta enfocada a encontrar texto normativo puntual.",
            QueryIntent.requirement_interpretation: "Consulta orientada a validar si algo cumple o es obligatorio.",
            QueryIntent.criteria_comparison: "Consulta comparativa entre criterios o normas.",
            QueryIntent.operational_compliance: "Consulta de aplicacion operativa en procesos y registros.",
        }
        for intent, confidence in sorted_items[:3]:
            if confidence <= 0:
                continue
            top.append(
                QueryInterpretation(
                    intent=intent,
                    confidence=round(confidence, 4),
                    rationale=rationales.get(intent, "Interpretacion probable de la consulta."),
                )
            )
        return top

    def analyze(
        self,
        *,
        question: str,
        history_messages: list[str] | None = None,
    ) -> QueryUnderstandingResult:
        history_messages = history_messages or []
        normalized = self.normalize_text(question)
        corrected = self.correct_text(normalized)
        terms = self.tokenize(corrected)
        expanded_terms = self.expand_terms(terms)

        entities = QueryEntities(
            norma_codigos=self.extract_norma_codes(corrected),
            numerales=NUMERAL_RE.findall(corrected),
            temas=self.extract_topics(expanded_terms),
        )

        inferred_from_history = False
        assumptions: list[str] = []
        if history_messages and (not entities.norma_codigos or not entities.temas):
            history_entities = self._infer_entities_from_history(history_messages)
            if not entities.norma_codigos and history_entities.norma_codigos:
                entities.norma_codigos = history_entities.norma_codigos
                inferred_from_history = True
                assumptions.append(
                    f"Se asume que la consulta refiere a {history_entities.norma_codigos[0]} por historial reciente."
                )
            if not entities.temas and history_entities.temas:
                entities.temas = history_entities.temas
                inferred_from_history = True
                assumptions.append(
                    f"Se asume continuidad del tema '{history_entities.temas[0]}' por contexto reciente."
                )

        domain_score = self._domain_score(expanded_terms, bool(entities.norma_codigos))
        domain_in_scope = domain_score >= 0.25

        intent_scores = self._intent_scores(corrected, expanded_terms, entities)
        ambiguity_score, ambiguity_signals = self._ambiguity(
            corrected,
            terms,
            entities,
            inferred_from_history,
        )

        interpretations = self._build_interpretations(intent_scores)
        top_intent = max(intent_scores.items(), key=lambda item: item[1], default=(QueryIntent.too_ambiguous, 0.0))

        if not domain_in_scope:
            intent = QueryIntent.out_of_domain
            intent_confidence = round(max(0.5, 1.0 - domain_score), 4)
        elif ambiguity_score >= 0.65 and (
            top_intent[1] < 0.65 or (not entities.norma_codigos and not entities.temas)
        ):
            intent = QueryIntent.too_ambiguous
            intent_confidence = round(max(0.5, ambiguity_score), 4)
        else:
            intent = top_intent[0]
            intent_confidence = round(top_intent[1], 4)

        if not intent_scores:
            intent_scores = {intent: intent_confidence}

        return QueryUnderstandingResult(
            raw_question=question,
            normalized_question=normalized,
            corrected_question=corrected,
            query_terms=terms[:12],
            expanded_terms=expanded_terms[:18],
            entities=entities,
            intent=intent,
            intent_confidence=float(intent_confidence),
            intent_scores=intent_scores,
            ambiguity_score=float(ambiguity_score),
            ambiguity_signals=ambiguity_signals,
            domain_score=float(domain_score),
            domain_in_scope=domain_in_scope,
            interpretation_candidates=interpretations,
            assumptions=assumptions,
        )
