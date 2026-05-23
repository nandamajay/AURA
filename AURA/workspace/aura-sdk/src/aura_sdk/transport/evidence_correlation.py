"""Deterministic multi-domain evidence correlation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class EvidenceCorrelationResult:
    evidence_lineage_graph: dict[str, Any]
    domain_snapshot: dict[str, Any]
    evidence_completeness: float
    mismatches: list[dict[str, Any]]
    evidence_gaps: list[str]
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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"1", "true", "yes", "on", "success", "ok"}
    return False


def _collect_refs(value: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    def add(items: Any) -> None:
        if isinstance(items, list):
            for item in items:
                add(item)
            return
        if isinstance(items, dict):
            for key in ("evidence_references", "references"):
                if key in items:
                    add(items.get(key))
            return
        text = str(items).strip()
        if not text or "://" not in text:
            return
        if text in seen:
            return
        seen.add(text)
        refs.append(text)

    add(value)
    return refs


def _domain_presence(domains: Mapping[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key, value in domains.items():
        if isinstance(value, dict):
            result[key] = bool(value)
        elif isinstance(value, list):
            result[key] = bool(value)
        else:
            result[key] = bool(value)
    return result


def correlate_evidence(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    pcm_activity: Mapping[str, Any],
    mixer_state: Mapping[str, Any],
    topology_cognition: Mapping[str, Any],
    dts_cognition: Mapping[str, Any],
    semantic_cognition: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    regression_history: list[Mapping[str, Any]],
    plugin_capability_state: Mapping[str, Any],
    governance_decisions: Mapping[str, Any],
    adapter_evidence: Mapping[str, Any],
) -> EvidenceCorrelationResult:
    runtime = _as_dict(runtime_evidence)
    pcm = _as_dict(pcm_activity)
    mixer = _as_dict(mixer_state)
    topo = _as_dict(topology_cognition)
    dts = _as_dict(dts_cognition)
    semantic = _as_dict(semantic_cognition)
    replay = _as_dict(replay_traces)
    capabilities = _as_dict(plugin_capability_state)
    governance = _as_dict(governance_decisions)
    adapters = _as_dict(adapter_evidence)

    domains = {
        "runtime_evidence": runtime,
        "pcm_activity": pcm,
        "mixer_state": mixer,
        "topology_cognition": topo,
        "dts_cognition": dts,
        "semantic_cognition": semantic,
        "replay_traces": replay,
        "regression_history": list(regression_history),
        "plugin_capability_state": capabilities,
        "governance_decisions": governance,
    }
    presence = _domain_presence(domains)
    total = len(presence)
    present = sum(1 for value in presence.values() if value)
    completeness = round((present / total) if total else 0.0, 3)
    gaps = sorted([name for name, ok in presence.items() if not ok])

    runtime_success = _to_bool(runtime.get("playback_completion")) or _to_bool(runtime.get("process_success"))
    if not runtime_success and runtime.get("playback_exit_code") == 0:
        runtime_success = True

    topology_conf = _to_float(_as_dict(topo.get("confidence")).get("topology_confidence", topo.get("topology_confidence", 0.0)))
    semantic_cls = str(_as_dict(semantic.get("classification")).get("primary_classification", "UNKNOWN"))
    replay_deterministic = _to_bool(replay.get("deterministic_event_ordering")) or bool(replay.get("deterministic_replay_fingerprint"))
    plugin_supported = _to_bool(capabilities.get("supported")) if "supported" in capabilities else True
    fail_closed = _to_bool(governance.get("fail_closed_posture", True))

    mismatches: list[dict[str, Any]] = []
    if runtime_success and topology_conf < 0.35:
        mismatches.append(
            {
                "code": "topology_runtime_mismatch",
                "severity": "MEDIUM",
                "details": "Runtime playback succeeded while topology confidence is low.",
            }
        )
    if runtime_success and not plugin_supported:
        mismatches.append(
            {
                "code": "plugin_capability_inconsistency",
                "severity": "HIGH",
                "details": "Runtime success conflicts with unsupported plugin capability state.",
            }
        )
    if semantic_cls in {"vendor_coupled", "governance_risky"} and not replay_deterministic:
        mismatches.append(
            {
                "code": "semantic_runtime_mismatch",
                "severity": "MEDIUM",
                "details": "Semantic risk classification paired with replay instability.",
            }
        )
    if fail_closed and _to_bool(governance.get("autonomous_patching_allowed", False)):
        mismatches.append(
            {
                "code": "governance_violation",
                "severity": "HIGH",
                "details": "Fail-closed governance conflicts with autonomous patching flag.",
            }
        )

    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": "runtime_evidence", "kind": "runtime_evidence"},
        {"id": "pcm_activity", "kind": "pcm_activity"},
        {"id": "mixer_state", "kind": "mixer_state"},
        {"id": "topology_cognition", "kind": "topology_cognition"},
        {"id": "dts_cognition", "kind": "dts_cognition"},
        {"id": "semantic_cognition", "kind": "semantic_cognition"},
        {"id": "replay_traces", "kind": "replay_traces"},
        {"id": "regression_history", "kind": "regression_history"},
        {"id": "plugin_capability_state", "kind": "plugin_capability_state"},
        {"id": "governance_decisions", "kind": "governance_decisions"},
    ]

    edges = [
        {"from": f"target:{target_id}", "to": "runtime_evidence", "relation": "observed_by"},
        {"from": "runtime_evidence", "to": "pcm_activity", "relation": "correlates_with"},
        {"from": "runtime_evidence", "to": "mixer_state", "relation": "correlates_with"},
        {"from": "dts_cognition", "to": "topology_cognition", "relation": "informs"},
        {"from": "semantic_cognition", "to": "runtime_evidence", "relation": "interprets"},
        {"from": "replay_traces", "to": "runtime_evidence", "relation": "validates"},
        {"from": "regression_history", "to": "runtime_evidence", "relation": "scores"},
        {"from": "plugin_capability_state", "to": "runtime_evidence", "relation": "bounds"},
        {"from": "governance_decisions", "to": "runtime_evidence", "relation": "enforces"},
    ]

    evidence_references = _collect_refs(
        {
            "runtime": runtime,
            "semantic": semantic,
            "replay": replay,
            "adapters": adapters,
        }
    )

    domain_snapshot = {
        "runtime_fingerprint": stable_fingerprint(runtime),
        "pcm_fingerprint": stable_fingerprint(pcm),
        "mixer_fingerprint": stable_fingerprint(mixer),
        "topology_fingerprint": stable_fingerprint(topo),
        "dts_fingerprint": stable_fingerprint(dts),
        "semantic_fingerprint": stable_fingerprint(semantic),
        "replay_fingerprint": stable_fingerprint(replay),
        "regression_fingerprint": stable_fingerprint({"regression_history": list(regression_history)}),
        "plugin_capability_fingerprint": stable_fingerprint(capabilities),
        "governance_fingerprint": stable_fingerprint(governance),
    }

    graph = {
        "schema_version": "1.0",
        "graph_name": "evidence_lineage_graph",
        "target_id": target_id,
        "domain_presence": presence,
        "evidence_completeness": completeness,
        "evidence_references": evidence_references,
        "nodes": nodes,
        "edges": edges,
        "mismatches": mismatches,
        "evidence_gaps": gaps,
        "adapter_fingerprints": {
            "runtime": stable_fingerprint(_as_dict(adapters.get("runtime"))),
            "topology": stable_fingerprint(_as_dict(adapters.get("topology"))),
            "semantic": stable_fingerprint(_as_dict(adapters.get("semantic"))),
        },
    }

    deterministic_fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "presence": presence,
            "domain_snapshot": domain_snapshot,
            "mismatches": mismatches,
            "gaps": gaps,
            "completeness": completeness,
        }
    )

    return EvidenceCorrelationResult(
        evidence_lineage_graph=graph,
        domain_snapshot=domain_snapshot,
        evidence_completeness=completeness,
        mismatches=mismatches,
        evidence_gaps=gaps,
        deterministic_fingerprint=deterministic_fingerprint,
    )
