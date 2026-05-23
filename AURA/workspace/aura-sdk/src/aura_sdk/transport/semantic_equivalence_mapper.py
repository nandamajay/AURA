"""Downstream/upstream semantic equivalence mapping from knowledge entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticEquivalenceMapResult:
    semantic_equivalence_map: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _default_map() -> dict[str, str]:
    return {
        "msm_": "snd_soc_component",
        "qcom_": "snd_soc_component",
        "wcd": "sound/soc/codecs/wcd*",
        "lpass": "sound/soc/qcom/lpass*",
        "swr_": "soundwire",
        "sdw_": "soundwire",
        "q6_": "generic_dsp_or_mailbox_abstraction",
        "apr_": "mailbox_or_ipc_abstraction",
        "gpr_": "mailbox_or_ipc_abstraction",
    }


def build_semantic_equivalence_map(
    *,
    source_id: str,
    source_version: str,
    semantic_entity_graph: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
) -> SemanticEquivalenceMapResult:
    graph = _as_dict(semantic_entity_graph)
    entities = _as_dict(graph.get("entity_categories"))
    adapter = _as_dict(adapter_payload)

    downstream = _dedupe([str(item) for item in _as_list(entities.get("qcom_downstream_abstractions"))])
    upstream_hint_entities = _dedupe([str(item) for item in _as_list(entities.get("upstream_equivalence_mappings"))])

    hints = _default_map()
    plugin_hints = _as_dict(adapter.get("upstream_equivalence_hints"))
    hints.update({str(key): str(value) for key, value in plugin_hints.items() if str(key).strip() and str(value).strip()})

    confidence_hints = _as_dict(adapter.get("equivalence_confidence_hints"))

    mappings: list[dict[str, Any]] = []
    for token in downstream:
        resolved = "UNRESOLVED"
        confidence = 0.2
        token_lower = token.lower()

        for key, value in hints.items():
            if token_lower.startswith(str(key).lower()) or str(key).lower() in token_lower:
                resolved = str(value)
                confidence = max(confidence, 0.72)
                break

        if resolved == "UNRESOLVED":
            for upstream in upstream_hint_entities:
                if upstream.lower() in token_lower or token_lower in upstream.lower():
                    resolved = upstream
                    confidence = max(confidence, 0.58)
                    break

        for hint_key, hint_conf in confidence_hints.items():
            if str(hint_key).lower() in token_lower:
                confidence = max(confidence, min(1.0, _to_float(hint_conf)))

        status = "EXACT" if resolved != "UNRESOLVED" and confidence >= 0.75 else ("PARTIAL" if resolved != "UNRESOLVED" else "UNRESOLVED")

        mappings.append(
            {
                "downstream_construct": token,
                "upstream_equivalent": resolved,
                "equivalence_status": status,
                "equivalence_confidence": round(confidence, 3),
            }
        )

    if not mappings:
        mappings.append(
            {
                "downstream_construct": "NONE_DETECTED",
                "upstream_equivalent": "UNRESOLVED",
                "equivalence_status": "UNRESOLVED",
                "equivalence_confidence": 0.0,
            }
        )

    average_confidence = round(
        sum(float(item.get("equivalence_confidence", 0.0)) for item in mappings) / max(1, len(mappings)),
        3,
    )

    payload = {
        "schema_version": "1.0",
        "report_name": "semantic_equivalence_map",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "average_equivalence_confidence": average_confidence,
        "mappings": mappings,
        "classification": "PASS" if average_confidence >= 0.55 else "ADVISORY_ONLY",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticEquivalenceMapResult(
        semantic_equivalence_map=payload,
        deterministic_fingerprint=fingerprint,
    )
