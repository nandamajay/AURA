"""Engineering query history model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class EngineeringQueryHistoryResult:
    engineering_query_history: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def update_engineering_query_history(
    *,
    session_id: str,
    previous_history: list[Mapping[str, Any]] | None,
    answer_entries: list[Mapping[str, Any]],
) -> EngineeringQueryHistoryResult:
    history = [row for row in _as_list(previous_history or []) if isinstance(row, dict)]

    for index, entry in enumerate(answer_entries, start=1):
        item = _as_dict(entry)
        history.append(
            {
                "sequence": len(history) + 1,
                "session_id": str(session_id),
                "question_id": str(item.get("question_id", f"q{index}")),
                "question": str(item.get("question", "")),
                "selected_resolver": str(item.get("selected_resolver", "")),
                "classification": str(item.get("classification", "UNKNOWN")),
                "confidence_score": float(item.get("confidence_score", 0.0) or 0.0),
                "answer_fingerprint": str(item.get("deterministic_fingerprint", "")),
            }
        )

    history = history[-20000:]

    payload = {
        "schema_version": "1.0",
        "report_name": "engineering_query_history",
        "session_id": str(session_id),
        "history": history,
        "summary": {
            "entry_count": len(history),
            "session_entry_count": len([row for row in history if str(_as_dict(row).get("session_id", "")) == str(session_id)]),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return EngineeringQueryHistoryResult(
        engineering_query_history=payload,
        deterministic_fingerprint=fingerprint,
    )
