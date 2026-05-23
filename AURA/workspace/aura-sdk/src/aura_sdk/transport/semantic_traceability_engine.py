"""Traceability and persistence for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticTraceabilityResult:
    semantic_traceability_graph: dict[str, Any]
    deterministic_fingerprint: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def build_semantic_traceability_graph(
    *,
    source_id: str,
    source_version: str,
    source_path: str,
    source_sha256: str,
    lineage_id: str,
    artifacts: Mapping[str, Any],
) -> SemanticTraceabilityResult:
    rows = {str(name): _as_dict(value) for name, value in sorted(_as_dict(artifacts).items())}

    nodes: list[dict[str, Any]] = [
        {
            "id": f"source:{source_id}",
            "kind": "semantic_source",
            "source_id": str(source_id),
            "source_version": str(source_version),
            "source_path": str(source_path),
            "source_sha256": str(source_sha256),
        },
        {
            "id": f"lineage:{lineage_id}",
            "kind": "semantic_lineage",
            "lineage_id": str(lineage_id),
            "recorded_at": _utc_now_iso(),
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "from": f"source:{source_id}",
            "to": f"lineage:{lineage_id}",
            "relation": "materialized_as",
        }
    ]

    for name, payload in rows.items():
        artifact_id = f"artifact:{name}"
        nodes.append(
            {
                "id": artifact_id,
                "kind": "semantic_artifact",
                "artifact_name": name,
                "fingerprint": str(payload.get("deterministic_fingerprint", "")),
                "classification": str(payload.get("classification", payload.get("report_name", payload.get("graph_name", "UNKNOWN")))),
            }
        )
        edges.append({"from": f"lineage:{lineage_id}", "to": artifact_id, "relation": "produced"})

    payload = {
        "schema_version": "1.0",
        "graph_name": "semantic_traceability_graph",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "lineage_id": str(lineage_id),
        "nodes": nodes,
        "edges": edges,
        "classification": "PASS" if rows else "ADVISORY_ONLY_EMPTY_TRACE",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticTraceabilityResult(
        semantic_traceability_graph=payload,
        deterministic_fingerprint=fingerprint,
    )


class KernelSemanticKnowledgeRegistry:
    """Replay-safe persistence for semantic knowledge layer artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "semantic_entity_graph": self._output_dir / "semantic_entity_graph.json",
            "semantic_relationship_map": self._output_dir / "semantic_relationship_map.json",
            "semantic_ontology": self._output_dir / "semantic_ontology.json",
            "semantic_portability_rules": self._output_dir / "semantic_portability_rules.json",
            "semantic_equivalence_map": self._output_dir / "semantic_equivalence_map.json",
            "semantic_runtime_advisories": self._output_dir / "semantic_runtime_advisories.json",
            "semantic_traceability_graph": self._output_dir / "semantic_traceability_graph.json",
            "semantic_confidence_report": self._output_dir / "semantic_confidence_report.json",
        }

    def persist(self, semantic_bundle: Mapping[str, Any]) -> dict[str, Any]:
        bundle = dict(semantic_bundle)
        artifacts = _as_dict(bundle.get("artifacts"))
        lineage_id = str(bundle.get("lineage_id", "")).strip() or stable_fingerprint(bundle)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry_payload = self._registry.load()
        state = _as_dict(registry_payload.get("kernel_semantic_knowledge_layer"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "source_id": str(bundle.get("source_id", "")),
            "source_version": str(bundle.get("source_version", "")),
            "source_sha256": str(bundle.get("source_sha256", "")),
            "semantic_knowledge_fingerprint": str(bundle.get("semantic_knowledge_fingerprint", "")),
            "artifact_paths": {key: str(path.resolve()) for key, path in paths.items()},
            "classification": str(_as_dict(artifacts.get("semantic_confidence_report")).get("classification", "UNKNOWN")),
            "evidence_references": [str(item) for item in _as_list(bundle.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-1500:]

        registry_payload["kernel_semantic_knowledge_layer"] = {
            "schema_version": "1.0",
            "latest": dict(bundle),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry_payload.setdefault("cognition_lineage", [])
        lineage = _as_list(registry_payload.get("cognition_lineage"))
        lineage.append(
            {
                "lineage_id": lineage_id,
                "type": "kernel_semantic_knowledge_layer",
                "recorded_at": _utc_now_iso(),
                "semantic_knowledge_fingerprint": str(bundle.get("semantic_knowledge_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry_payload["cognition_lineage"] = lineage[-6000:]
        registry_payload["updated_at"] = _utc_now_iso()

        self._registry.save(registry_payload)

        return {
            "lineage_id": lineage_id,
            "semantic_knowledge_fingerprint": str(bundle.get("semantic_knowledge_fingerprint", "")),
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry_payload = self._registry.load()
        state = _as_dict(registry_payload.get("kernel_semantic_knowledge_layer"))
        history = _as_list(state.get("history"))

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                entry = _as_dict(row)
                if str(entry.get("lineage_id", "")) == str(lineage_id):
                    selected = entry
                    break

        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "kernel_semantic_knowledge_layer",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "semantic_knowledge_fingerprint": str(_as_dict(selected).get("semantic_knowledge_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "semantic_knowledge_fingerprint": str(_as_dict(selected).get("semantic_knowledge_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "semantic_knowledge_replay_trace.json", replay_payload)
        return replay_payload
