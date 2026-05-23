"""Plugin drift detection utilities for portable runtime stabilization."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def detect_plugin_drift(
    *,
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    base = _as_dict(baseline)
    cur = _as_dict(current)

    base_cap = _as_dict(base.get("capabilities"))
    cur_cap = _as_dict(cur.get("capabilities"))

    mutated_capabilities: list[dict[str, str]] = []
    cap_keys = sorted(set(base_cap).union(cur_cap))
    for key in cap_keys:
        old = str(base_cap.get(key, "UNKNOWN"))
        new = str(cur_cap.get(key, "UNKNOWN"))
        if old != new:
            mutated_capabilities.append({"capability": key, "before": old, "after": new})

    base_top = str(base.get("topology_contract_fingerprint", ""))
    cur_top = str(cur.get("topology_contract_fingerprint", ""))
    topology_contract_drift = bool(base_top and cur_top and base_top != cur_top)

    base_replay = str(base.get("replay_compatibility", "UNKNOWN"))
    cur_replay = str(cur.get("replay_compatibility", "UNKNOWN"))
    replay_incompatibility = base_replay in {"FULL", "PARTIAL"} and cur_replay == "INCOMPATIBLE"

    base_evidence = _as_dict(base.get("evidence_schema"))
    cur_evidence = _as_dict(cur.get("evidence_schema"))
    evidence_schema_drift = bool(base_evidence and cur_evidence and _stable_hash(base_evidence) != _stable_hash(cur_evidence))

    drift_detected = bool(mutated_capabilities or topology_contract_drift or replay_incompatibility or evidence_schema_drift)
    return {
        "schema_version": "1.0",
        "drift_detected": drift_detected,
        "capability_mutations": mutated_capabilities,
        "topology_contract_drift": topology_contract_drift,
        "replay_incompatibility": replay_incompatibility,
        "evidence_schema_drift": evidence_schema_drift,
        "classification": "DRIFTED" if drift_detected else "STABLE",
    }
