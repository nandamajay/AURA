"""SoundWire runtime graph extraction for offline runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SoundwireRuntimeGraphResult:
    soundwire_runtime_graph: dict[str, Any]
    soundwire_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_soundwire_runtime_graph(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> SoundwireRuntimeGraphResult:
    ingestion = _as_dict(runtime_event_ingestion)
    topology = _as_dict(topology_runtime_graph)

    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]
    swr_events = [row for row in events if str(row.get("category", "")) == "soundwire"]

    nodes: list[dict[str, Any]] = [{"id": f"target:{target_id}", "kind": "target"}]
    edges: list[dict[str, Any]] = []

    for index, event in enumerate(swr_events, start=1):
        event_id = str(event.get("event_id", f"soundwire:{index}"))
        node_id = f"soundwire_event:{event_id}"
        nodes.append(
            {
                "id": node_id,
                "kind": "soundwire_event",
                "timestamp_ms": float(event.get("timestamp_ms", 0.0) or 0.0),
                "detail": str(event.get("detail", "")),
            }
        )
        edges.append(
            {
                "from": f"target:{target_id}",
                "to": node_id,
                "relation": "observed_soundwire_event",
            }
        )

    for row in _as_list(topology.get("edges")):
        edge = _as_dict(row)
        src = str(edge.get("from", "")).strip()
        dst = str(edge.get("to", "")).strip()
        if not src or not dst:
            continue
        if "be:" in src.lower() or "be:" in dst.lower() or "soundwire" in src.lower() or "soundwire" in dst.lower():
            edges.append(
                {
                    "from": src,
                    "to": dst,
                    "relation": "topology_runtime_link",
                }
            )

    dedup_nodes = {str(node.get("id", "")): node for node in nodes if str(node.get("id", "")).strip()}

    soundwire_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.7 * min(1.0, len(swr_events) / 6.0) + 0.3 * min(1.0, len(edges) / 20.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if len(swr_events) == 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "graph_name": "soundwire_runtime_graph",
        "target_id": str(target_id),
        "classification": classification,
        "soundwire_confidence": soundwire_confidence,
        "nodes": list(dedup_nodes.values()),
        "edges": edges,
        "summary": {
            "runtime_soundwire_events": len(swr_events),
            "graph_node_count": len(dedup_nodes),
            "graph_edge_count": len(edges),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SoundwireRuntimeGraphResult(
        soundwire_runtime_graph=payload,
        soundwire_confidence=soundwire_confidence,
        deterministic_fingerprint=fingerprint,
    )
