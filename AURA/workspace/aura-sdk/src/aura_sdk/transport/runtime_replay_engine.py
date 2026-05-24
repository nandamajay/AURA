"""Deterministic runtime replay lineage and cross-session consistency."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeReplayResult:
    runtime_replay_registry: dict[str, Any]
    replay_consistency_report: dict[str, Any]


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


class RuntimeReplayEngine:
    """Validate deterministic runtime replay lineage and cross-session drift."""

    def evaluate(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        deterministic_runtime_replay: Mapping[str, Any],
        runtime_equivalence_fingerprint: Mapping[str, Any],
        runtime_governance_decision: Mapping[str, Any],
        previous_registry_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> RuntimeReplayResult:
        replay = _as_dict(deterministic_runtime_replay)
        eq_fp = _as_dict(runtime_equivalence_fingerprint)
        gov = _as_dict(runtime_governance_decision)
        history = [_as_dict(row) for row in (previous_registry_history or []) if isinstance(row, Mapping)]
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        replay_signal = _as_dict(replay.get("replay_signal"))
        deterministic_ready = bool(replay_signal.get("deterministic_event_ordering", False))
        replay_fingerprint = str(replay.get("deterministic_fingerprint", ""))
        eq_fingerprint = str(eq_fp.get("deterministic_fingerprint", ""))
        gov_fingerprint = str(gov.get("deterministic_fingerprint", ""))

        lineage_fingerprint = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "runtime_replay_fingerprint": replay_fingerprint,
                "runtime_equivalence_fingerprint": eq_fingerprint,
                "runtime_governance_fingerprint": gov_fingerprint,
            }
        )

        previous_entry = history[-1] if history else {}
        previous_lineage_fingerprint = str(_as_dict(previous_entry).get("lineage_fingerprint", ""))
        replay_drift = bool(previous_lineage_fingerprint and previous_lineage_fingerprint != lineage_fingerprint)

        consistency_reasons: list[str] = []
        if not deterministic_ready:
            consistency_reasons.append("deterministic_event_ordering_unproven")
        if not replay_fingerprint:
            consistency_reasons.append("runtime_replay_fingerprint_missing")
        if not eq_fingerprint:
            consistency_reasons.append("runtime_equivalence_fingerprint_missing")
        if replay_drift:
            consistency_reasons.append("cross_session_replay_drift_detected")

        classification = "FAIL_CLOSED" if consistency_reasons else "PASS"

        entry = {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "target_id": str(target_id),
            "recorded_at": _utc_now_iso(),
            "classification": classification,
            "lineage_fingerprint": lineage_fingerprint,
            "runtime_replay_fingerprint": replay_fingerprint,
            "runtime_equivalence_fingerprint": eq_fingerprint,
            "runtime_governance_fingerprint": gov_fingerprint,
            "deterministic_event_ordering": deterministic_ready,
            "replay_drift": replay_drift,
        }
        history.append(entry)
        history = history[-4096:]

        runtime_replay_registry = {
            "schema_version": "1.0",
            "report_name": "runtime_replay_registry",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "latest_entry": entry,
            "history": history,
            "summary": {
                "history_count": len(history),
                "deterministic_ready": deterministic_ready,
                "replay_drift": replay_drift,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_replay_registry["deterministic_fingerprint"] = stable_fingerprint(runtime_replay_registry)

        replay_consistency_report = {
            "schema_version": "1.0",
            "report_name": "replay_consistency_report",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "reasons": consistency_reasons,
            "consistency": {
                "deterministic_event_ordering": deterministic_ready,
                "lineage_fingerprint": lineage_fingerprint,
                "previous_lineage_fingerprint": previous_lineage_fingerprint,
                "replay_drift": replay_drift,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        replay_consistency_report["deterministic_fingerprint"] = stable_fingerprint(replay_consistency_report)

        return RuntimeReplayResult(
            runtime_replay_registry=runtime_replay_registry,
            replay_consistency_report=replay_consistency_report,
        )


class RuntimeReplayRegistry:
    """Persistence for runtime replay artifacts and lineage history."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "runtime_replay_registry": self._output_dir / "runtime_replay_registry.json",
            "replay_consistency_report": self._output_dir / "replay_consistency_report.json",
        }

    def load_history(self) -> list[dict[str, Any]]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_cognition_replay"))
        return [_as_dict(row) for row in _as_list(state.get("history")) if isinstance(row, Mapping)]

    def persist(
        self,
        *,
        runtime_replay_registry: Mapping[str, Any],
        replay_consistency_report: Mapping[str, Any],
    ) -> dict[str, Any]:
        paths = self._artifact_paths()
        _save_json(paths["runtime_replay_registry"], _as_dict(runtime_replay_registry))
        _save_json(paths["replay_consistency_report"], _as_dict(replay_consistency_report))

        registry = self._registry.load()
        replay_state = _as_dict(registry.get("runtime_cognition_replay"))
        history = [_as_dict(row) for row in _as_list(replay_state.get("history")) if isinstance(row, Mapping)]
        entry = {
            "lineage_id": str(_as_dict(runtime_replay_registry).get("lineage_id", "")),
            "session_id": str(_as_dict(runtime_replay_registry).get("session_id", "")),
            "classification": str(_as_dict(runtime_replay_registry).get("classification", "UNKNOWN")),
            "lineage_fingerprint": str(_as_dict(_as_dict(runtime_replay_registry).get("latest_entry")).get("lineage_fingerprint", "")),
            "deterministic_fingerprint": str(_as_dict(runtime_replay_registry).get("deterministic_fingerprint", "")),
            "recorded_at": _utc_now_iso(),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
        }
        history.append(entry)
        history = history[-8000:]

        registry["runtime_cognition_replay"] = {
            "schema_version": "1.0",
            "latest": dict(runtime_replay_registry),
            "history": history,
            "updated_at": _utc_now_iso(),
        }
        registry.setdefault("cognition_lineage", [])
        lineages = [_as_dict(row) for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, Mapping)]
        lineages.append(
            {
                "lineage_id": entry["lineage_id"],
                "type": "runtime_cognition_replay",
                "recorded_at": _utc_now_iso(),
                "deterministic_fingerprint": entry["deterministic_fingerprint"],
            }
        )
        registry["cognition_lineage"] = lineages[-40000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": entry["lineage_id"],
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        replay_state = _as_dict(registry.get("runtime_cognition_replay"))
        history = [_as_dict(row) for row in _as_list(replay_state.get("history")) if isinstance(row, Mapping)]

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
            "replay_type": "runtime_cognition_replay",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "deterministic_fingerprint": str(_as_dict(selected).get("deterministic_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "deterministic_fingerprint": str(_as_dict(selected).get("deterministic_fingerprint", "")),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        return replay_payload
