"""Replay-safe semantic persistence backed by the cognition registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


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


class SemanticCognitionRegistry:
    """Persist semantic cognition outputs deterministically and replay safely."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "downstream_semantic_graph": self._output_dir / "downstream_semantic_graph.json",
            "subsystem_mapping_graph": self._output_dir / "subsystem_mapping_graph.json",
            "dts_topology_graph": self._output_dir / "dts_topology_graph.json",
            "vendor_dependency_fingerprint": self._output_dir / "vendor_dependency_fingerprint.json",
            "semantic_confidence_report": self._output_dir / "semantic_confidence_report.json",
        }

    def persist(self, semantic_bundle: Mapping[str, Any]) -> dict[str, Any]:
        bundle = dict(semantic_bundle)
        artifacts = _as_dict(bundle.get("artifacts"))
        lineage_id = str(bundle.get("lineage_id", "")).strip() or stable_fingerprint(bundle)

        paths = self._artifact_paths()
        for key, path in paths.items():
            payload = _as_dict(artifacts.get(key))
            _save_json(path, payload)

        registry_payload = self._registry.load()
        semantic_state = _as_dict(registry_payload.get("semantic_cognition"))
        history = _as_list(semantic_state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(bundle.get("target_id", "")),
            "semantic_fingerprint": str(bundle.get("semantic_fingerprint", "")),
            "classification": _as_dict(bundle.get("classification")),
            "replay_compatibility": str(bundle.get("replay_compatibility", "UNKNOWN")),
            "evidence_references": [str(item) for item in _as_list(bundle.get("evidence_references")) if str(item).strip()],
            "artifact_paths": {key: str(path.resolve()) for key, path in paths.items()},
        }
        history.append(entry)
        history = history[-1000:]

        registry_payload["semantic_cognition"] = {
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
                "type": "semantic_cognition",
                "recorded_at": _utc_now_iso(),
                "semantic_fingerprint": str(bundle.get("semantic_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry_payload["cognition_lineage"] = lineage[-2000:]
        self._registry.save(registry_payload)

        return {
            "lineage_id": lineage_id,
            "artifact_paths": {key: str(path.resolve()) for key, path in paths.items()},
            "semantic_fingerprint": str(bundle.get("semantic_fingerprint", "")),
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry_payload = self._registry.load()
        semantic_state = _as_dict(registry_payload.get("semantic_cognition"))
        history = _as_list(semantic_state.get("history"))

        selected = None
        if lineage_id:
            for item in reversed(history):
                row = _as_dict(item)
                if str(row.get("lineage_id", "")) == str(lineage_id):
                    selected = row
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        latest_bundle = _as_dict(semantic_state.get("latest"))
        if selected:
            selected_fingerprint = str(selected.get("semantic_fingerprint", ""))
            if selected_fingerprint and str(latest_bundle.get("semantic_fingerprint", "")) != selected_fingerprint:
                # Replay-safe: select matching historical snapshot if latest differs.
                candidates = [item for item in history if _as_dict(item).get("semantic_fingerprint") == selected_fingerprint]
                if candidates:
                    selected = _as_dict(candidates[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "semantic_cognition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "semantic_fingerprint": str(_as_dict(selected).get("semantic_fingerprint", "")),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "semantic_fingerprint": str(_as_dict(selected).get("semantic_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "semantic_replay_trace.json", replay_payload)
        return replay_payload
