from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_qa_battery import IMPROVEMENTS, build_cases, evaluate_case  # noqa: E402


API_BASE_URL = os.getenv("QA_API_BASE_URL", "http://localhost:8000")
ENDPOINT = f"{API_BASE_URL.rstrip('/')}/chat/query"
TIMEOUT_SECONDS = float(os.getenv("QA_HTTP_TIMEOUT_SECONDS", "90"))
USE_LLM = os.getenv("QA_USE_LLM", "true").strip().lower() == "true"
TOP_K = int(os.getenv("QA_TOP_K", "6"))


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            data = response.read().decode("utf-8")
            return response.status, json.loads(data)
    except error.HTTPError as exc:
        data = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = {"raw": data}
        return exc.code, {"error": parsed}
    except Exception as exc:  # network/timeout
        return 0, {"error": {"detail": str(exc)}}


def clip(text: str, limit: int = 320) -> str:
    return " ".join((text or "").split())[:limit]


def main() -> None:
    cases = build_cases()
    results: list[dict] = []

    for case in cases:
        payload = {
            "question": case.question,
            "top_k": TOP_K,
            "use_llm": USE_LLM,
            "history": [{"role": "user", "content": item} for item in (case.history or [])],
        }
        status, response = post_json(ENDPOINT, payload)

        if status == 200:
            response_info = {
                "response_mode": response.get("response_mode", "execution_error"),
                "support_level": response.get("support_level", "n/a"),
                "detected_intent": response.get("detected_intent", "n/a"),
                "intent_confidence": response.get("intent_confidence", 0.0),
                "ambiguity_score": response.get("ambiguity_score", 0.0),
                "confidence_score": response.get("confidence_score", 0.0),
                "confidence_level": response.get("confidence_level", "low"),
                "llm_used": bool(response.get("llm_used", False)),
                "references": len(response.get("references", [])),
                "clarification_options": len((response.get("clarification") or {}).get("options", [])),
                "answer_excerpt": clip(response.get("answer", "")),
                "decision_reasons": response.get("decision_reasons", []),
            }
            scores, result, risk, err = evaluate_case(case, response_info)
            results.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "category": case.category,
                    "objective": case.objective,
                    "expected_behavior": case.expected_behavior,
                    "expected_modes": case.expected_modes,
                    "system_response": response_info,
                    "scores": scores,
                    "result": result,
                    "risk": risk,
                    "error": err,
                    "improvement_possible": err != "no_improvement_needed",
                    "improvement": IMPROVEMENTS[err],
                    "priority": "Alta" if risk == "ALTO" else ("Media" if risk == "MEDIO" else "Baja"),
                    "consistency_group": case.consistency_group,
                }
            )
        else:
            detail = response.get("error", {})
            results.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "category": case.category,
                    "objective": case.objective,
                    "expected_behavior": case.expected_behavior,
                    "expected_modes": case.expected_modes,
                    "system_response": {
                        "response_mode": "execution_error",
                        "support_level": "n/a",
                        "detected_intent": "n/a",
                        "intent_confidence": 0.0,
                        "ambiguity_score": 0.0,
                        "confidence_score": 0.0,
                        "confidence_level": "low",
                        "llm_used": False,
                        "references": 0,
                        "clarification_options": 0,
                        "answer_excerpt": clip(json.dumps(detail, ensure_ascii=False)),
                        "decision_reasons": [f"http_status_{status}"],
                    },
                    "scores": {
                        "Comprension de intencion": 1,
                        "Manejo de ambiguedad": 1,
                        "Precision": 1,
                        "Claridad": 1,
                        "Utilidad": 1,
                        "Seguridad": 1,
                        "Apego al dominio": 1,
                        "Aclaracion correcta": 1,
                        "Consistencia": 1,
                        "Calidad general": 1.0,
                    },
                    "result": "FAIL",
                    "risk": "ALTO",
                    "error": "runtime_error",
                    "improvement_possible": True,
                    "improvement": "Revisar logs backend/LLM y resiliencia de endpoint para evitar errores 5xx/timeout.",
                    "priority": "Alta",
                    "consistency_group": case.consistency_group,
                }
            )

    group_map: dict[str, list[dict]] = defaultdict(list)
    for item in results:
        group = item["consistency_group"]
        if group:
            group_map[group].append(item)

    for _, items in group_map.items():
        dominant_mode = Counter(item["system_response"]["response_mode"] for item in items).most_common(1)[0][0]
        dominant_intent = Counter(item["system_response"]["detected_intent"] for item in items).most_common(1)[0][0]
        conf_values = [item["system_response"]["confidence_score"] for item in items]
        conf_range = (max(conf_values) - min(conf_values)) if conf_values else 0.0

        for item in items:
            consistency = 5
            if item["system_response"]["response_mode"] != dominant_mode:
                consistency -= 2
            if item["system_response"]["detected_intent"] != dominant_intent:
                consistency -= 1
            if conf_range > 0.45:
                consistency -= 1
            consistency = max(1, consistency)
            item["scores"]["Consistencia"] = consistency

            avg = round(sum(v for k, v in item["scores"].items() if k != "Calidad general") / 9, 2)
            item["scores"]["Calidad general"] = avg
            if consistency <= 2 and item["error"] == "no_improvement_needed":
                item["error"] = "inconsistency_error"
                item["improvement_possible"] = True
                item["improvement"] = IMPROVEMENTS["inconsistency_error"]

            critical = item["error"] in {"domain_guardrail_failure", "unsupported_answer", "hallucination_risk", "runtime_error"}
            if critical or avg < 2.8:
                item["result"] = "FAIL"
                item["risk"] = "ALTO"
                item["priority"] = "Alta"
            elif avg >= 4.0 and item["error"] == "no_improvement_needed":
                item["result"] = "PASS"
                item["risk"] = "BAJO"
                item["priority"] = "Baja"
            else:
                item["result"] = "PARTIAL"
                item["risk"] = "MEDIO"
                item["priority"] = "Media"

    expected_mode_adherence = sum(1 for item in results if item["system_response"]["response_mode"] in item["expected_modes"]) / len(results)
    summary = {
        "total": len(results),
        "result_counts": dict(Counter(item["result"] for item in results)),
        "error_counts": dict(Counter(item["error"] for item in results)),
        "mode_counts": dict(Counter(item["system_response"]["response_mode"] for item in results)),
        "avg_quality": round(sum(item["scores"]["Calidad general"] for item in results) / len(results), 2),
        "avg_confidence": round(sum(item["system_response"]["confidence_score"] for item in results) / len(results), 3),
        "llm_used_count": int(sum(1 for item in results if item["system_response"].get("llm_used"))),
        "expected_mode_adherence": round(expected_mode_adherence, 3),
        "endpoint": ENDPOINT,
        "use_llm": USE_LLM,
        "top_k": TOP_K,
    }

    payload = {"summary": summary, "results": results}
    with open("qa_results_http_llm.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
