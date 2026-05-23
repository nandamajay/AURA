"""AURA internal agentization architecture for persistent cognition runtime.

Agents are coordinated exclusively through machine-readable shared cognition
state. No hidden prompt memory is used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine
from aura_sdk.transport.cognitive_persistence import (
    AURAArtifactIndexEngine,
    AURACognitionBootLoader,
    AURACognitionPortability,
    AURACognitionRegistry,
    AURAGovernanceEngine,
    AURAPhaseEngine,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _stable_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _health(
    *,
    agent: str,
    ok: bool,
    reasons: list[str],
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "status": "HEALTHY" if ok else "DEGRADED",
        "ok": ok,
        "reasons": reasons,
        "details": dict(details or {}),
        "updated_at": _utc_now_iso(),
    }


def _default_agent_runtime() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "board": "RB3Gen2",
        "cognition_version": "1.0.0",
        "agent_protocol_version": "1.0.0",
        "active_agents": [],
        "agent_health": {},
        "agent_state": {},
        "protocol_messages": [],
        "state_machine": {
            "current_state": "bootstrapped",
            "allowed_transitions": [
                "bootstrapped->governance_validated",
                "governance_validated->runtime_validated",
                "runtime_validated->topology_validated",
                "topology_validated->regression_evaluated",
                "regression_evaluated->persistence_synced",
            ],
            "transition_history": [],
        },
        "updated_at": _utc_now_iso(),
    }


def _append_protocol_message(
    runtime: dict[str, Any],
    *,
    source_agent: str,
    target_agent: str,
    message_type: str,
    payload: Mapping[str, Any],
) -> None:
    message = {
        "message_id": _stable_hash(
            {
                "source_agent": source_agent,
                "target_agent": target_agent,
                "message_type": message_type,
                "payload": dict(payload),
                "at": _utc_now_iso(),
            }
        ),
        "source_agent": source_agent,
        "target_agent": target_agent,
        "message_type": message_type,
        "payload": dict(payload),
        "timestamp": _utc_now_iso(),
    }
    runtime.setdefault("protocol_messages", []).append(message)
    runtime["protocol_messages"] = _coerce_list(runtime.get("protocol_messages"))[-500:]


def _agent_definitions() -> dict[str, dict[str, Any]]:
    return {
        "runtime_agent": {
            "agent_id": "runtime_agent",
            "role": "runtime_orchestration",
            "responsibilities": [
                "playback_orchestration",
                "capture_orchestration",
                "pcm_evidence_collection",
                "runtime_validation",
                "execution_sequencing",
                "procedural_replay_execution",
            ],
            "capability_boundaries": {
                "allowed": [
                    "read_runtime_traces",
                    "read_procedural_memory",
                    "emit_runtime_validation_state",
                ],
                "blocked": [
                    "autonomous_patching",
                    "autonomous_topology_rewrite",
                    "unsupervised_runtime_mutation",
                    "automatic_upstream_generation",
                ],
            },
        },
        "topology_agent": {
            "agent_id": "topology_agent",
            "role": "topology_reasoning",
            "responsibilities": [
                "fe_be_correlation",
                "dtsi_parsing",
                "dapm_graph_reasoning",
                "soundwire_cognition",
                "overlay_mutation_tracking",
                "route_graph_generation",
            ],
            "capability_boundaries": {
                "allowed": [
                    "read_topology_artifacts",
                    "read_runtime_correlation",
                    "emit_topology_confidence",
                ],
                "blocked": [
                    "self_modifying_topology",
                    "route_guessing_without_evidence",
                    "topology_rewriting",
                ],
            },
        },
        "governance_agent": {
            "agent_id": "governance_agent",
            "role": "policy_enforcement",
            "responsibilities": [
                "fail_closed_enforcement",
                "execution_policy",
                "command_allowlists",
                "write_approvals",
                "autonomous_action_restrictions",
                "transport_validation",
            ],
            "capability_boundaries": {
                "allowed": [
                    "enforce_phase_scope",
                    "enforce_governance_state",
                    "emit_policy_decisions",
                ],
                "blocked": [
                    "disable_fail_closed_without_state_change",
                    "silent_policy_mutation",
                ],
            },
        },
        "regression_agent": {
            "agent_id": "regression_agent",
            "role": "drift_and_confidence_analysis",
            "responsibilities": [
                "deterministic_replay_scoring",
                "drift_detection",
                "timing_regression",
                "route_instability_analysis",
                "confidence_evolution",
                "replay_comparison",
            ],
            "capability_boundaries": {
                "allowed": [
                    "read_regression_lineage",
                    "read_runtime_and_topology_confidence",
                    "emit_regression_summary",
                ],
                "blocked": [
                    "runtime_mutation",
                    "topology_mutation",
                ],
            },
        },
        "persistence_agent": {
            "agent_id": "persistence_agent",
            "role": "state_durability_and_portability",
            "responsibilities": [
                "cognition_registry_management",
                "boot_reconstruction",
                "cognition_lineage",
                "artifact_indexing",
                "portability_snapshots",
                "procedural_memory_persistence",
            ],
            "capability_boundaries": {
                "allowed": [
                    "read_write_registry",
                    "refresh_artifact_index",
                    "export_import_portable_snapshot",
                ],
                "blocked": [
                    "modify_runtime_execution_path",
                    "alter_governance_constraints_implicitly",
                ],
            },
        },
    }


@dataclass(frozen=True)
class AgentizationResult:
    agent_runtime: dict[str, Any]
    architecture: dict[str, Any]
    capability_graph: dict[str, Any]
    state_machine: dict[str, Any]
    inter_agent_protocol: dict[str, Any]
    cognition_versioning: dict[str, Any]
    cognition_bus_architecture: dict[str, Any]
    event_flow_graph: dict[str, Any]
    replay_lifecycle_graph: dict[str, Any]
    event_persistence_schema: dict[str, Any]
    confidence_propagation_model: dict[str, Any]
    event_lineage: dict[str, Any]
    agent_sync_state: dict[str, Any]


class AURAInternalAgentizationCoordinator:
    """Coordinator for internal specialized cognition agents."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        cognition_registry_path: str | Path,
        phase_state_path: str | Path,
        governance_state_path: str | Path,
        baseline_registry_path: str | Path,
        procedural_memory_path: str | Path,
        procedural_lock_path: str | Path,
        procedural_route_memory_path: str | Path,
        runtime_report_path: str | Path,
        artifact_index_path: str | Path,
        portable_snapshot_path: str | Path,
    ):
        self._output_dir = Path(output_dir)
        self._registry_path = Path(cognition_registry_path)
        self._phase_state_path = Path(phase_state_path)
        self._governance_state_path = Path(governance_state_path)
        self._baseline_registry_path = Path(baseline_registry_path)
        self._procedural_memory_path = Path(procedural_memory_path)
        self._procedural_lock_path = Path(procedural_lock_path)
        self._procedural_route_memory_path = Path(procedural_route_memory_path)
        self._runtime_report_path = Path(runtime_report_path)
        self._artifact_index_path = Path(artifact_index_path)
        self._portable_snapshot_path = Path(portable_snapshot_path)
        self._event_schema_path = self._output_dir / "aura_event_schema.json"
        self._event_lineage_path = self._output_dir / "aura_event_lineage.json"
        self._agent_sync_state_path = self._output_dir / "aura_agent_sync_state.json"
        self._cognition_bus = AURACognitionBus(
            output_dir=self._output_dir,
            lineage_path=self._event_lineage_path,
            agent_sync_state_path=self._agent_sync_state_path,
            schema_path=self._event_schema_path,
        )

    def _emit_bus_event(
        self,
        runtime: dict[str, Any],
        *,
        category: str,
        event_name: str,
        source_agent: str,
        target_agent: str,
        payload: Mapping[str, Any],
        confidence: float,
        evidence_references: list[str],
        governance_classification: str = "ADVISORY_ONLY",
    ) -> dict[str, Any]:
        lineage_id = _stable_hash(
            {
                "source_agent": source_agent,
                "target_agent": target_agent,
                "event_name": event_name,
                "category": category,
                "payload": dict(payload),
            }
        )
        replay_correlation_id = str(runtime.get("replay_correlation_id", ""))
        observer_kwargs = {
            "event_name": event_name,
            "originating_agent": source_agent,
            "target_agent": target_agent,
            "payload": payload,
            "confidence": confidence,
            "evidence_references": evidence_references,
            "cognition_lineage_id": lineage_id,
            "replay_correlation_id": replay_correlation_id,
            "governance_classification": governance_classification,
        }
        if category == "runtime":
            event = self._cognition_bus.observe_runtime(**observer_kwargs)
        elif category == "topology":
            event = self._cognition_bus.observe_topology(**observer_kwargs)
        elif category == "governance":
            event = self._cognition_bus.observe_governance(**observer_kwargs)
        elif category == "regression":
            event = self._cognition_bus.observe_regression(**observer_kwargs)
        elif category == "persistence":
            event = self._cognition_bus.observe_persistence(**observer_kwargs)
        elif category == "transport":
            event = self._cognition_bus.observe_transport(**observer_kwargs)
        else:
            event = self._cognition_bus.process_event(category=category, **observer_kwargs)
        _append_protocol_message(
            runtime,
            source_agent=source_agent,
            target_agent=target_agent,
            message_type=event_name,
            payload={
                "event_id": str(event.get("event_id", "")),
                "event_category": category,
                **dict(payload),
            },
        )
        return event

    def _runtime_agent(self, registry: Mapping[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        trace = _load_json_if_exists(self._output_dir / "rb3_runtime_procedural_execution_trace.json")
        correlation = _load_json_if_exists(self._output_dir / "rb3_runtime_validation_correlation_live.json")
        lock = _load_json_if_exists(self._procedural_lock_path)
        process_success = bool(trace.get("process_success", False))
        evidence_success = bool(trace.get("evidence_success", False))
        deterministic_sequence = bool(_coerce_list(lock.get("successful_execution_sequence")))
        ok = process_success and evidence_success and deterministic_sequence
        reasons = []
        if not process_success:
            reasons.append("process_success_false")
        if not evidence_success:
            reasons.append("evidence_success_false")
        if not deterministic_sequence:
            reasons.append("missing_procedural_sequence")
        if not reasons:
            reasons = ["runtime_flow_stable"]

        payload = {
            "current_state": str(trace.get("state_machine", {}).get("current_state", trace.get("current_state", ""))),
            "classification": str(trace.get("classification", "ADVISORY_ONLY")),
            "process_success": process_success,
            "evidence_success": evidence_success,
            "route_activation_confidence": str(correlation.get("route_activation_confidence", "LOW")),
            "playback_completion": bool(correlation.get("playback_completion", False)),
            "execution_sequence_length": len(_coerce_list(lock.get("successful_execution_sequence"))),
            "command_ordering_length": len(_coerce_list(lock.get("command_ordering"))),
        }
        runtime.setdefault("agent_state", {})["runtime_agent"] = payload
        runtime.setdefault("agent_health", {})["runtime_agent"] = _health(
            agent="runtime_agent",
            ok=ok,
            reasons=reasons,
            details=payload,
        )
        self._emit_bus_event(
            runtime,
            category="runtime",
            event_name="runtime_validation_state",
            source_agent="runtime_agent",
            target_agent="topology_agent",
            payload={
                "trace_path": str((self._output_dir / "rb3_runtime_procedural_execution_trace.json").resolve()),
                "process_success": process_success,
                "evidence_success": evidence_success,
            },
            confidence=1.0 if ok else 0.0,
            evidence_references=[
                str((self._output_dir / "rb3_runtime_procedural_execution_trace.json").resolve()),
                str((self._output_dir / "rb3_runtime_validation_correlation_live.json").resolve()),
            ],
            governance_classification="GOVERNED_APPROVED",
        )
        self._emit_bus_event(
            runtime,
            category="transport",
            event_name="transport_runtime_observed",
            source_agent="runtime_agent",
            target_agent="governance_agent",
            payload={
                "runtime_state": str(payload.get("current_state", "")),
                "execution_sequence_length": int(payload.get("execution_sequence_length", 0)),
                "playback_completion": bool(payload.get("playback_completion", False)),
            },
            confidence=1.0 if bool(payload.get("playback_completion", False)) else 0.5,
            evidence_references=[str((self._output_dir / "rb3_runtime_procedural_execution_trace.json").resolve())],
            governance_classification="GOVERNED_APPROVED",
        )
        return payload

    def _topology_agent(self, registry: Mapping[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        confidence = _load_json_if_exists(self._output_dir / "topology_confidence_report.json")
        route_graph = _load_json_if_exists(self._output_dir / "runtime_route_graph.json")
        topology_graph = _load_json_if_exists(self._output_dir / "topology_graph.json")
        state = str(confidence.get("topology_state", "LOW_CONFIDENCE"))
        score = float(confidence.get("topology_confidence", 0.0))
        ok = state in {"CONFIRMED", "INFERRED"} and score >= 0.50
        reasons = ["topology_state_" + state.lower()]
        if not ok:
            reasons.append("topology_confidence_low")
        payload = {
            "topology_state": state,
            "topology_confidence": score,
            "targeted_interrogation_mode": bool(confidence.get("targeted_interrogation_mode", False)),
            "targeted_questions": _coerce_list(confidence.get("targeted_questions")),
            "runtime_state_transitions": _coerce_list(_coerce_dict(route_graph.get("runtime_activation")).get("runtime_state_transitions")),
            "graph_nodes": len(_coerce_list(topology_graph.get("nodes"))),
            "graph_edges": len(_coerce_list(topology_graph.get("edges"))),
        }
        runtime.setdefault("agent_state", {})["topology_agent"] = payload
        runtime.setdefault("agent_health", {})["topology_agent"] = _health(
            agent="topology_agent",
            ok=ok,
            reasons=reasons,
            details=payload,
        )
        self._emit_bus_event(
            runtime,
            category="topology",
            event_name="topology_validation_state",
            source_agent="topology_agent",
            target_agent="regression_agent",
            payload={
                "topology_confidence_report_path": str((self._output_dir / "topology_confidence_report.json").resolve()),
                "topology_state": state,
                "topology_confidence": score,
            },
            confidence=score,
            evidence_references=[
                str((self._output_dir / "topology_confidence_report.json").resolve()),
                str((self._output_dir / "runtime_route_graph.json").resolve()),
            ],
            governance_classification="GOVERNED_APPROVED",
        )
        return payload

    def _governance_agent(self, registry: Mapping[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        phase_state = _load_json_if_exists(self._phase_state_path)
        governance_state = _load_json_if_exists(self._governance_state_path)
        phase = AURAPhaseEngine(phase_state)
        governance = AURAGovernanceEngine(governance_state)
        ok = True
        reasons: list[str] = []
        try:
            phase.assert_execution_scope("board:RB3Gen2")
            phase.assert_execution_scope("workflow:playback")
            phase.assert_execution_scope("transport:adb_shell")
            phase.assert_capability("rb3_playback_execution")
            governance.assert_action(
                action="rb3_controlled_playback",
                execution_mode="governed_write_approved",
                allow_write_ops=True,
                transport_mode="adb_shell",
            )
            reasons.append("fail_closed_enforced")
        except PermissionError as exc:
            ok = False
            reasons.append(str(exc))

        payload = {
            "fail_closed_posture": bool(governance.state.get("fail_closed_posture", True)),
            "write_policy": str(governance.state.get("write_policy", "UNKNOWN")),
            "execution_approval_mode": str(governance.state.get("execution_approval_mode", "UNKNOWN")),
            "blocked_capabilities": _coerce_list(phase.state.get("blocked_capabilities")),
            "allowed_execution_scope": _coerce_list(phase.state.get("allowed_execution_scope")),
        }
        runtime.setdefault("agent_state", {})["governance_agent"] = payload
        runtime.setdefault("agent_health", {})["governance_agent"] = _health(
            agent="governance_agent",
            ok=ok,
            reasons=reasons,
            details=payload,
        )
        self._emit_bus_event(
            runtime,
            category="governance",
            event_name="policy_verdict",
            source_agent="governance_agent",
            target_agent="runtime_agent",
            payload={"allowed": ok, "reason_chain": reasons},
            confidence=1.0 if ok else 0.0,
            evidence_references=[
                str(Path(self._phase_state_path).resolve()),
                str(Path(self._governance_state_path).resolve()),
            ],
            governance_classification="FAIL_CLOSED" if ok else "REJECTED",
        )
        return payload

    def _regression_agent(self, registry: Mapping[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        regression = _load_json_if_exists(self._output_dir / "rb3gen2_regression_fingerprint.json")
        drift = _load_json_if_exists(self._output_dir / "playback_drift_report.json")
        confidence = _load_json_if_exists(self._output_dir / "runtime_confidence_report.json")
        topology_confidence = _load_json_if_exists(self._output_dir / "topology_confidence_report.json")

        replay_conf = float(confidence.get("runtime_confidence", 0.0))
        topo_conf = float(topology_confidence.get("topology_confidence", 0.0))
        regression_detected = bool(regression.get("regression_detected", False))
        drift_detected = bool(drift.get("playback_timing_drift_detected", False))
        ok = (not regression_detected) and (not drift_detected)
        reasons = []
        if regression_detected:
            reasons.append("regression_detected")
        if drift_detected:
            reasons.append("playback_timing_drift_detected")
        if not reasons:
            reasons.append("deterministic_replay_stable")

        payload = {
            "deterministic_replay_score": round((0.7 * replay_conf) + (0.3 * topo_conf), 3),
            "runtime_confidence": replay_conf,
            "topology_confidence": topo_conf,
            "regression_detected": regression_detected,
            "regression_severity": str(regression.get("severity", "NONE")),
            "playback_timing_drift_detected": drift_detected,
            "route_instability_detected": bool(drift.get("route_instability_detected", False)),
            "degraded_evidence_runs": _coerce_list(drift.get("degraded_evidence_runs")),
        }
        runtime.setdefault("agent_state", {})["regression_agent"] = payload
        runtime.setdefault("agent_health", {})["regression_agent"] = _health(
            agent="regression_agent",
            ok=ok,
            reasons=reasons,
            details=payload,
        )
        self._emit_bus_event(
            runtime,
            category="regression",
            event_name="regression_summary",
            source_agent="regression_agent",
            target_agent="persistence_agent",
            payload={
                "regression_report_path": str((self._output_dir / "rb3gen2_regression_fingerprint.json").resolve()),
                "deterministic_replay_score": payload["deterministic_replay_score"],
            },
            confidence=float(payload["deterministic_replay_score"]),
            evidence_references=[
                str((self._output_dir / "rb3gen2_regression_fingerprint.json").resolve()),
                str((self._output_dir / "playback_drift_report.json").resolve()),
            ],
            governance_classification="GOVERNED_APPROVED",
        )
        return payload

    def _persistence_agent(self, registry: Mapping[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        loader = AURACognitionBootLoader(
            registry_path=self._registry_path,
            phase_state_path=self._phase_state_path,
            governance_state_path=self._governance_state_path,
            output_dir=self._output_dir,
            runtime_report_path=self._runtime_report_path,
            baseline_registry_path=self._baseline_registry_path,
            procedural_memory_path=self._procedural_memory_path,
            procedural_lock_path=self._procedural_lock_path,
            procedural_route_memory_path=self._procedural_route_memory_path,
        )
        boot = loader.boot()
        artifact_index = AURAArtifactIndexEngine(
            index_path=self._artifact_index_path,
            artifact_root=self._output_dir,
        ).refresh()
        portability = AURACognitionPortability().export_snapshot(
            output_path=self._portable_snapshot_path,
            registry=boot.registry,
            phase_state=boot.phase_state,
            governance_state=boot.governance_state,
            artifact_index=artifact_index,
            artifact_root=self._output_dir,
        )

        ok = bool(boot.boot_summary.get("execution_policies_restored", False)) and bool(portability)
        reasons = ["persistence_synced"] if ok else ["persistence_sync_failed"]
        payload = {
            "boot_summary": boot.boot_summary,
            "artifact_count": len(_coerce_list(artifact_index.get("artifacts"))),
            "portable_snapshot_path": str(Path(self._portable_snapshot_path).resolve()),
            "registry_path": str(Path(self._registry_path).resolve()),
            "phase_state_path": str(Path(self._phase_state_path).resolve()),
            "governance_state_path": str(Path(self._governance_state_path).resolve()),
        }
        runtime.setdefault("agent_state", {})["persistence_agent"] = payload
        runtime.setdefault("agent_health", {})["persistence_agent"] = _health(
            agent="persistence_agent",
            ok=ok,
            reasons=reasons,
            details=payload,
        )
        self._emit_bus_event(
            runtime,
            category="persistence",
            event_name="persistence_status",
            source_agent="persistence_agent",
            target_agent="governance_agent",
            payload={"registry_updated": ok, "artifact_count": payload["artifact_count"]},
            confidence=1.0 if ok else 0.0,
            evidence_references=[
                str(Path(self._registry_path).resolve()),
                str(Path(self._artifact_index_path).resolve()),
            ],
            governance_classification="GOVERNED_APPROVED",
        )
        return payload

    def _update_state_machine(self, runtime: dict[str, Any]) -> None:
        sm = _coerce_dict(runtime.get("state_machine"))
        sm.setdefault("allowed_transitions", _coerce_list(_default_agent_runtime()["state_machine"]["allowed_transitions"]))
        history = _coerce_list(sm.get("transition_history"))
        current = "bootstrapped"
        health = _coerce_dict(runtime.get("agent_health"))
        governance_ok = _coerce_dict(health.get("governance_agent")).get("ok", False)
        runtime_ok = _coerce_dict(health.get("runtime_agent")).get("ok", False)
        topology_ok = _coerce_dict(health.get("topology_agent")).get("ok", False)
        regression_ok = _coerce_dict(health.get("regression_agent")).get("ok", False)
        persistence_ok = _coerce_dict(health.get("persistence_agent")).get("ok", False)

        if governance_ok:
            history.append({"transition": "bootstrapped->governance_validated", "at": _utc_now_iso()})
            current = "governance_validated"
        if governance_ok and runtime_ok:
            history.append({"transition": "governance_validated->runtime_validated", "at": _utc_now_iso()})
            current = "runtime_validated"
        if governance_ok and runtime_ok and topology_ok:
            history.append({"transition": "runtime_validated->topology_validated", "at": _utc_now_iso()})
            current = "topology_validated"
        if governance_ok and runtime_ok and topology_ok and regression_ok:
            history.append({"transition": "topology_validated->regression_evaluated", "at": _utc_now_iso()})
            current = "regression_evaluated"
        if governance_ok and runtime_ok and topology_ok and regression_ok and persistence_ok:
            history.append({"transition": "regression_evaluated->persistence_synced", "at": _utc_now_iso()})
            current = "persistence_synced"

        sm["current_state"] = current
        sm["transition_history"] = history[-1000:]
        runtime["state_machine"] = sm

    def run_cycle(self) -> AgentizationResult:
        registry_store = AURACognitionRegistry(self._registry_path)
        registry = registry_store.load()
        runtime = _coerce_dict(registry.get("agent_runtime"))
        if not runtime:
            runtime = _default_agent_runtime()
        runtime.setdefault(
            "replay_correlation_id",
            _stable_hash({"board": "RB3Gen2", "at": _utc_now_iso(), "mode": "agentization_cycle"}),
        )
        runtime["active_agents"] = list(_agent_definitions().keys())
        runtime["agent_capability_boundaries"] = {
            agent: _coerce_dict(spec.get("capability_boundaries"))
            for agent, spec in _agent_definitions().items()
        }

        self._governance_agent(registry, runtime)
        self._runtime_agent(registry, runtime)
        self._topology_agent(registry, runtime)
        self._regression_agent(registry, runtime)
        self._persistence_agent(registry, runtime)
        self._update_state_machine(runtime)
        replayed_ids = self._cognition_bus.replay_persisted_events(actor="aura_event_replay_engine")
        event_lineage = self._cognition_bus.persist_lineage()
        event_ordering = self._cognition_bus.validate_ordering()
        confidence_model = self._cognition_bus.get_confidence_propagation_model()
        replay_engine = AURAEventReplayEngine(
            lineage_path=self._event_lineage_path,
            sync_state_path=self._agent_sync_state_path,
        )
        agent_sync_state = replay_engine.reconstruct()
        runtime["event_bus"] = {
            "event_count": int(event_lineage.get("ordering_validation", {}).get("event_count", 0)),
            "quarantine_count": int(event_lineage.get("ordering_validation", {}).get("quarantine_count", 0)),
            "replayed_event_count": len(replayed_ids),
            "ordering_valid": bool(event_ordering.get("valid", False)),
            "lineage_path": str(self._event_lineage_path.resolve()),
            "agent_sync_state_path": str(self._agent_sync_state_path.resolve()),
        }
        runtime["updated_at"] = _utc_now_iso()

        architecture = self._build_architecture(runtime)
        capability_graph = self._build_capability_graph()
        state_machine = _coerce_dict(runtime.get("state_machine"))
        protocol = self._build_protocol(runtime)
        versioning = self._build_versioning(runtime)
        bus_architecture = self._cognition_bus.build_cognition_bus_architecture()
        event_flow_graph = self._cognition_bus.build_event_flow_graph()
        replay_lifecycle_graph = self._cognition_bus.build_replay_lifecycle_graph()
        event_schema = self._cognition_bus.event_schema

        registry["agent_runtime"] = runtime
        registry["agent_architecture"] = architecture
        registry["agent_capability_graph"] = capability_graph
        registry["agent_state_machine"] = state_machine
        registry["inter_agent_protocol"] = protocol
        registry["cognition_versioning"] = versioning
        registry["cognition_bus_architecture"] = bus_architecture
        registry["event_flow_graph"] = event_flow_graph
        registry["replay_lifecycle_graph"] = replay_lifecycle_graph
        registry["event_persistence_schema"] = event_schema
        registry["confidence_propagation_model"] = confidence_model
        registry["event_lineage"] = event_lineage
        registry["agent_sync_state"] = agent_sync_state
        registry["updated_at"] = _utc_now_iso()
        registry_store.save(registry)

        return AgentizationResult(
            agent_runtime=runtime,
            architecture=architecture,
            capability_graph=capability_graph,
            state_machine=state_machine,
            inter_agent_protocol=protocol,
            cognition_versioning=versioning,
            cognition_bus_architecture=bus_architecture,
            event_flow_graph=event_flow_graph,
            replay_lifecycle_graph=replay_lifecycle_graph,
            event_persistence_schema=event_schema,
            confidence_propagation_model=confidence_model,
            event_lineage=event_lineage,
            agent_sync_state=agent_sync_state,
        )

    def _build_architecture(self, runtime: Mapping[str, Any]) -> dict[str, Any]:
        definitions = _agent_definitions()
        return {
            "schema_version": "1.0",
            "board": "RB3Gen2",
            "architecture_name": "AURA_Internal_Agentization_Runtime",
            "coordination_model": "shared_persistent_cognition_state",
            "memory_model": "machine_readable_registry_only",
            "agents": list(definitions.values()),
            "health": _coerce_dict(runtime.get("agent_health")),
            "state_source_of_truth": str(self._registry_path.resolve()),
            "fail_closed": True,
            "updated_at": _utc_now_iso(),
        }

    def _build_capability_graph(self) -> dict[str, Any]:
        defs = _agent_definitions()
        nodes: list[dict[str, str]] = []
        edges: list[dict[str, str]] = []
        for agent, spec in defs.items():
            nodes.append({"id": agent, "kind": "agent", "label": str(spec.get("role", agent))})
            for cap in _coerce_list(spec.get("responsibilities")):
                cap_id = f"cap:{agent}:{cap}"
                nodes.append({"id": cap_id, "kind": "capability", "label": str(cap)})
                edges.append({"from": agent, "to": cap_id, "relation": "owns_capability"})
            for blocked in _coerce_list(_coerce_dict(spec.get("capability_boundaries")).get("blocked")):
                blk_id = f"blocked:{agent}:{blocked}"
                nodes.append({"id": blk_id, "kind": "restriction", "label": str(blocked)})
                edges.append({"from": agent, "to": blk_id, "relation": "blocked_capability"})
        dedup = {node["id"]: node for node in nodes}
        return {
            "schema_version": "1.0",
            "nodes": list(dedup.values()),
            "edges": edges,
            "updated_at": _utc_now_iso(),
        }

    def _build_protocol(self, runtime: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "protocol_version": "1.0.0",
            "transport": "registry_backed_json_messages",
            "message_schema": {
                "message_id": "sha256",
                "source_agent": "string",
                "target_agent": "string",
                "message_type": "string",
                "payload": "object",
                "timestamp": "iso8601",
            },
            "message_types": [
                "policy_verdict",
                "runtime_validation_state",
                "transport_runtime_observed",
                "topology_validation_state",
                "regression_summary",
                "persistence_status",
            ],
            "messages": _coerce_list(runtime.get("protocol_messages")),
            "updated_at": _utc_now_iso(),
        }

    def _build_versioning(self, runtime: Mapping[str, Any]) -> dict[str, Any]:
        defs = _agent_definitions()
        component_versions = {
            "cognition_registry_schema": "1.0.0",
            "inter_agent_protocol": "1.0.0",
            "runtime_agent": "1.0.0",
            "topology_agent": "1.0.0",
            "governance_agent": "1.0.0",
            "regression_agent": "1.0.0",
            "persistence_agent": "1.0.0",
        }
        compatibility = {
            "portable_snapshot_version": "1.0.0",
            "requires_fail_closed": True,
            "board_scope": ["RB3Gen2"],
            "blocked_features": [
                "autonomous_patching",
                "self_modifying_topology",
                "unsupervised_runtime_mutation",
                "automatic_upstream_generation",
            ],
        }
        return {
            "schema_version": "1.0",
            "cognition_version": "1.0.0",
            "component_versions": component_versions,
            "agent_count": len(defs),
            "compatibility": compatibility,
            "updated_at": _utc_now_iso(),
        }

    def export_architecture_artifacts(self, result: AgentizationResult) -> dict[str, str]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        architecture_path = self._output_dir / "aura_agent_architecture.json"
        capability_graph_path = self._output_dir / "aura_agent_capability_graph.json"
        state_machine_path = self._output_dir / "aura_agent_state_machine.json"
        protocol_path = self._output_dir / "aura_inter_agent_protocol.json"
        versioning_path = self._output_dir / "aura_cognition_versioning.json"
        bus_architecture_path = self._output_dir / "aura_cognition_bus_architecture.json"
        event_flow_path = self._output_dir / "aura_event_flow_graph.json"
        replay_lifecycle_path = self._output_dir / "aura_replay_lifecycle_graph.json"
        persistence_schema_path = self._output_dir / "aura_event_persistence_schema.json"
        confidence_model_path = self._output_dir / "aura_confidence_propagation_model.json"

        _save_json(architecture_path, result.architecture)
        _save_json(capability_graph_path, result.capability_graph)
        _save_json(state_machine_path, result.state_machine)
        _save_json(protocol_path, result.inter_agent_protocol)
        _save_json(versioning_path, result.cognition_versioning)
        _save_json(bus_architecture_path, result.cognition_bus_architecture)
        _save_json(event_flow_path, result.event_flow_graph)
        _save_json(replay_lifecycle_path, result.replay_lifecycle_graph)
        _save_json(persistence_schema_path, result.event_persistence_schema)
        _save_json(confidence_model_path, result.confidence_propagation_model)

        bus_paths = self._cognition_bus.export_bus_artifacts()
        _save_json(self._event_lineage_path, result.event_lineage)
        _save_json(self._agent_sync_state_path, result.agent_sync_state)

        return {
            "aura_agent_architecture": str(architecture_path.resolve()),
            "aura_agent_capability_graph": str(capability_graph_path.resolve()),
            "aura_agent_state_machine": str(state_machine_path.resolve()),
            "aura_inter_agent_protocol": str(protocol_path.resolve()),
            "aura_cognition_versioning": str(versioning_path.resolve()),
            "aura_cognition_bus_architecture": str(bus_architecture_path.resolve()),
            "aura_event_flow_graph": str(event_flow_path.resolve()),
            "aura_replay_lifecycle_graph": str(replay_lifecycle_path.resolve()),
            "aura_event_persistence_schema": str(persistence_schema_path.resolve()),
            "aura_confidence_propagation_model": str(confidence_model_path.resolve()),
            **bus_paths,
        }
