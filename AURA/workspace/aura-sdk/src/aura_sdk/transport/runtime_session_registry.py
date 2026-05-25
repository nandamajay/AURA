"""Runtime session registry for real evidence ingestion lineage."""

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


class RuntimeSessionRegistry:
    """Replay-safe persistence for runtime evidence ingestion session artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "normalized_runtime_evidence": self._output_dir / "normalized_runtime_evidence.json",
            "runtime_session_graph": self._output_dir / "runtime_session_graph.json",
            "evidence_capture_lineage": self._output_dir / "evidence_capture_lineage.json",
            "subsystem_runtime_state": self._output_dir / "subsystem_runtime_state.json",
            "dsp_runtime_trace": self._output_dir / "dsp_runtime_trace.json",
            "soundwire_runtime_trace": self._output_dir / "soundwire_runtime_trace.json",
            "pcm_runtime_state": self._output_dir / "pcm_runtime_state.json",
            "runtime_discovery_report": self._output_dir / "runtime_discovery_report.json",
            "runtime_toolchain_discovery": self._output_dir / "runtime_toolchain_discovery.json",
            "hardware_topology_graph": self._output_dir / "hardware_topology_graph.json",
            "audio_component_lineage_map": self._output_dir / "audio_component_lineage_map.json",
            "runtime_evidence_snapshots": self._output_dir / "runtime_evidence_snapshots.json",
            "inferred_playback_route_graph": self._output_dir / "inferred_playback_route_graph.json",
            "inferred_capture_route_graph": self._output_dir / "inferred_capture_route_graph.json",
            "mixer_dependency_report": self._output_dir / "mixer_dependency_report.json",
            "real_playback_observability_timeline": self._output_dir / "real_playback_observability_timeline.json",
            "offline_runtime_replay_foundation": self._output_dir / "offline_runtime_replay_foundation.json",
            "runtime_capture_fingerprint": self._output_dir / "runtime_capture_fingerprint.json",
            "deterministic_runtime_session_replay": self._output_dir / "deterministic_runtime_session_replay.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_ingestion"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "runtime_evidence_ingestion_fingerprint": str(payload.get("runtime_evidence_ingestion_fingerprint", "")),
            "runtime_sequence_fingerprint": str(
                _as_dict(artifacts.get("offline_runtime_replay_foundation")).get("runtime_sequence_fingerprint", "")
            ),
            "normalized_event_count": int(
                _as_dict(_as_dict(artifacts.get("normalized_runtime_evidence")).get("summary")).get(
                    "normalized_event_count", 0
                )
                or 0
            ),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-6000:]

        registry["runtime_evidence_ingestion"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineages = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "runtime_evidence_ingestion",
                "recorded_at": _utc_now_iso(),
                "runtime_evidence_ingestion_fingerprint": str(payload.get("runtime_evidence_ingestion_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-15000:]

        registry.setdefault("runtime_session_lineage", [])
        session_lineage = [row for row in _as_list(registry.get("runtime_session_lineage")) if isinstance(row, dict)]
        session_lineage.append(
            {
                "lineage_id": lineage_id,
                "session_id": entry["session_id"],
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "runtime_evidence_ingestion_fingerprint": entry["runtime_evidence_ingestion_fingerprint"],
            }
        )
        registry["runtime_session_lineage"] = session_lineage[-8000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "runtime_evidence_ingestion_fingerprint": entry["runtime_evidence_ingestion_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_ingestion"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "runtime_evidence_ingestion",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "runtime_evidence_ingestion_fingerprint": str(_as_dict(selected).get("runtime_evidence_ingestion_fingerprint", "")),
            "runtime_sequence_fingerprint": str(_as_dict(selected).get("runtime_sequence_fingerprint", "")),
            "normalized_event_count": int(_as_dict(selected).get("normalized_event_count", 0) or 0),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "runtime_evidence_ingestion_fingerprint": str(_as_dict(selected).get("runtime_evidence_ingestion_fingerprint", "")),
                    "runtime_sequence_fingerprint": str(_as_dict(selected).get("runtime_sequence_fingerprint", "")),
                    "normalized_event_count": int(_as_dict(selected).get("normalized_event_count", 0) or 0),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_runtime_session_replay.json", replay_payload)
        return replay_payload
