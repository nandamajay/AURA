"""Runtime governance gating driven by live/runtime evidence cognition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_RUNTIME_CONFIDENCE_THRESHOLD = 0.78


@dataclass(frozen=True)
class RuntimeGovernanceResult:
    runtime_governance_decision: dict[str, Any]
    runtime_escalation_report: dict[str, Any]
    runtime_risk_report: dict[str, Any]


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "pass", "ok"}
    return False


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


class RuntimeGovernanceEngine:
    """Apply fail-closed governance policy to runtime cognition outputs."""

    def evaluate(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        governance_state: Mapping[str, Any],
        runtime_equivalence_report: Mapping[str, Any],
        runtime_divergence_report: Mapping[str, Any],
        runtime_confidence_report: Mapping[str, Any],
        deterministic_runtime_replay: Mapping[str, Any],
        runtime_sensitive_impact_count: int,
        previous_confidence_history: list[float] | None,
        evidence_references: list[str] | None,
    ) -> RuntimeGovernanceResult:
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]
        gov = _as_dict(governance_state)
        eq = _as_dict(runtime_equivalence_report)
        div = _as_dict(runtime_divergence_report)
        conf = _as_dict(runtime_confidence_report)
        replay = _as_dict(deterministic_runtime_replay)

        confidence_score = _to_float(conf.get("confidence_score"), 0.0)
        divergence_count = int(_as_dict(div.get("summary")).get("diverged_dimension_count", 0))
        critical_divergence_count = int(_as_dict(div.get("summary")).get("critical_divergence_count", 0))
        deterministic_replay_ready = _is_true(_as_dict(replay.get("replay_signal")).get("deterministic_event_ordering", False))

        escalation_reasons: list[str] = []
        if not _is_true(gov.get("fail_closed_posture", True)):
            escalation_reasons.append("governance_fail_closed_posture_disabled")
        if _is_true(gov.get("autonomous_runtime_mutation_allowed", False)):
            escalation_reasons.append("governance_runtime_mutation_not_allowed")
        if _is_true(gov.get("autonomous_upstream_generation_allowed", False)):
            escalation_reasons.append("governance_autonomous_generation_not_allowed")
        if confidence_score < _RUNTIME_CONFIDENCE_THRESHOLD:
            escalation_reasons.append("runtime_confidence_below_threshold")
        if critical_divergence_count > 0:
            escalation_reasons.append("critical_runtime_divergence_detected")
        if runtime_sensitive_impact_count > 0:
            escalation_reasons.append("runtime_sensitive_region_instability")
        if not deterministic_replay_ready:
            escalation_reasons.append("deterministic_runtime_replay_unproven")
        if str(div.get("classification", "PASS")) != "PASS":
            escalation_reasons.append("runtime_divergence_fail_closed")
        if str(conf.get("classification", "PASS")) != "PASS":
            escalation_reasons.append("runtime_confidence_fail_closed")

        history = [float(v) for v in (previous_confidence_history or [])]
        history.append(confidence_score)
        history = history[-128:]
        confidence_delta = 0.0
        if len(history) >= 2:
            confidence_delta = round(history[-1] - history[-2], 6)

        risk_score = min(1.0, round((1.0 - confidence_score) + (critical_divergence_count * 0.12), 6))
        risk_band = "low"
        if risk_score >= 0.7:
            risk_band = "high"
        elif risk_score >= 0.4:
            risk_band = "medium"

        classification = "FAIL_CLOSED" if escalation_reasons else "PASS"
        promotion_eligible = classification == "PASS"

        runtime_risk_report = {
            "schema_version": "1.0",
            "report_name": "runtime_risk_report",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "risk_score": risk_score,
            "risk_band": risk_band,
            "risk_inputs": {
                "confidence_score": confidence_score,
                "divergence_count": divergence_count,
                "critical_divergence_count": critical_divergence_count,
                "runtime_sensitive_impact_count": int(runtime_sensitive_impact_count),
                "deterministic_replay_ready": deterministic_replay_ready,
                "confidence_delta": confidence_delta,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_risk_report["deterministic_fingerprint"] = stable_fingerprint(runtime_risk_report)

        runtime_escalation_report = {
            "schema_version": "1.0",
            "report_name": "runtime_escalation_report",
            "target_id": str(target_id),
            "classification": classification,
            "escalation_reasons": sorted(set(escalation_reasons)),
            "escalation_count": len(sorted(set(escalation_reasons))),
            "cumulative_runtime_confidence_history": history,
            "cumulative_runtime_confidence": {
                "current": confidence_score,
                "delta": confidence_delta,
                "window": len(history),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_escalation_report["deterministic_fingerprint"] = stable_fingerprint(runtime_escalation_report)

        runtime_governance_decision = {
            "schema_version": "1.0",
            "report_name": "runtime_governance_decision",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "promotion_eligible": promotion_eligible,
            "fail_closed_reasons": sorted(set(escalation_reasons)),
            "runtime_promotion_gate": {
                "confidence_threshold": _RUNTIME_CONFIDENCE_THRESHOLD,
                "confidence_score": confidence_score,
                "runtime_sensitive_impact_count": int(runtime_sensitive_impact_count),
                "critical_divergence_count": critical_divergence_count,
                "deterministic_replay_ready": deterministic_replay_ready,
            },
            "runtime_inputs": {
                "runtime_equivalence_fingerprint": str(_as_dict(eq).get("deterministic_fingerprint", "")),
                "runtime_divergence_fingerprint": str(_as_dict(div).get("deterministic_fingerprint", "")),
                "runtime_confidence_fingerprint": str(_as_dict(conf).get("deterministic_fingerprint", "")),
                "runtime_replay_fingerprint": str(_as_dict(replay).get("deterministic_fingerprint", "")),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_governance_decision["deterministic_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": runtime_governance_decision["classification"],
                "promotion_eligible": runtime_governance_decision["promotion_eligible"],
                "fail_closed_reasons": runtime_governance_decision["fail_closed_reasons"],
                "runtime_promotion_gate": runtime_governance_decision["runtime_promotion_gate"],
                "runtime_inputs": runtime_governance_decision["runtime_inputs"],
            }
        )

        return RuntimeGovernanceResult(
            runtime_governance_decision=runtime_governance_decision,
            runtime_escalation_report=runtime_escalation_report,
            runtime_risk_report=runtime_risk_report,
        )


class RuntimeGovernanceRegistry:
    """Persistence for runtime governance artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "runtime_governance_decision": self._output_dir / "runtime_governance_decision.json",
            "runtime_escalation_report": self._output_dir / "runtime_escalation_report.json",
            "runtime_risk_report": self._output_dir / "runtime_risk_report.json",
        }

    def load_confidence_history(self) -> list[float]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_governance"))
        out: list[float] = []
        for row in _as_list(state.get("history")):
            item = _as_dict(row)
            try:
                out.append(float(item.get("confidence_score", 0.0)))
            except (TypeError, ValueError):
                out.append(0.0)
        return out

    def persist(
        self,
        *,
        runtime_governance_decision: Mapping[str, Any],
        runtime_escalation_report: Mapping[str, Any],
        runtime_risk_report: Mapping[str, Any],
    ) -> dict[str, Any]:
        paths = self._artifact_paths()
        _save_json(paths["runtime_governance_decision"], _as_dict(runtime_governance_decision))
        _save_json(paths["runtime_escalation_report"], _as_dict(runtime_escalation_report))
        _save_json(paths["runtime_risk_report"], _as_dict(runtime_risk_report))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_governance"))
        history = [_as_dict(row) for row in _as_list(state.get("history")) if isinstance(row, Mapping)]

        decision = _as_dict(runtime_governance_decision)
        gate = _as_dict(decision.get("runtime_promotion_gate"))
        entry = {
            "lineage_id": str(decision.get("lineage_id", "")),
            "session_id": str(decision.get("session_id", "")),
            "target_id": str(decision.get("target_id", "")),
            "classification": str(decision.get("classification", "UNKNOWN")),
            "confidence_score": float(gate.get("confidence_score", 0.0)),
            "promotion_eligible": bool(decision.get("promotion_eligible", False)),
            "fail_closed_reasons": [str(v) for v in _as_list(decision.get("fail_closed_reasons")) if str(v).strip()],
            "deterministic_fingerprint": str(decision.get("deterministic_fingerprint", "")),
            "recorded_at": _utc_now_iso(),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
        }
        history.append(entry)
        history = history[-8000:]

        registry["runtime_governance"] = {
            "schema_version": "1.0",
            "latest": dict(runtime_governance_decision),
            "history": history,
            "updated_at": _utc_now_iso(),
        }
        registry.setdefault("cognition_lineage", [])
        lineages = [_as_dict(row) for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, Mapping)]
        lineages.append(
            {
                "lineage_id": entry["lineage_id"],
                "type": "runtime_governance",
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
            "promotion_eligible": entry["promotion_eligible"],
            "artifact_paths": entry["artifact_paths"],
        }
