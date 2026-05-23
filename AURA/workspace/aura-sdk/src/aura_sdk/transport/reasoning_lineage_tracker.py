"""Reasoning lineage tracker for deterministic investigation sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class ReasoningLineageResult:
    runtime_question_lineage: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_reasoning_lineage(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    previous_lineage: list[Mapping[str, Any]] | None,
    answer_entries: list[Mapping[str, Any]],
    evidence_references: list[str] | None,
) -> ReasoningLineageResult:
    previous = [row for row in _as_list(previous_lineage or []) if isinstance(row, dict)]
    chain = previous[-4000:]

    prev_hash = str(_as_dict(chain[-1]).get("entry_hash", "")) if chain else ""
    for idx, entry in enumerate(answer_entries, start=1):
        item = _as_dict(entry)
        lineage_entry = {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "question_id": str(item.get("question_id", f"q{idx}")),
            "question": str(item.get("question", "")),
            "selected_resolver": str(item.get("selected_resolver", "")),
            "classification": str(item.get("classification", "UNKNOWN")),
            "confidence_score": float(item.get("confidence_score", 0.0) or 0.0),
            "answer_fingerprint": str(item.get("deterministic_fingerprint", "")),
            "previous_hash": prev_hash,
        }
        entry_hash = stable_fingerprint(lineage_entry)
        lineage_entry["entry_hash"] = entry_hash
        prev_hash = entry_hash
        chain.append(lineage_entry)

    chain = chain[-8000:]

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_question_lineage",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "lineage": chain,
        "summary": {
            "lineage_entry_count": len(chain),
            "final_chain_hash": prev_hash,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return ReasoningLineageResult(
        runtime_question_lineage=payload,
        deterministic_fingerprint=fingerprint,
    )
