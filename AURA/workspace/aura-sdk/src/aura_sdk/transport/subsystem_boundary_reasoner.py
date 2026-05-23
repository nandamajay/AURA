"""Subsystem boundary reasoning for maintainership-safe patch decomposition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SubsystemBoundaryResult:
    subsystem_boundary_map: dict[str, Any]
    boundary_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _classify_subsystem(token: str) -> str:
    lowered = str(token).lower()
    if "soundwire" in lowered or "swr" in lowered:
        return "soundwire"
    if "dsp" in lowered or "adsp" in lowered or "qdsp" in lowered or "apr" in lowered:
        return "dsp"
    if "topology" in lowered or "dai" in lowered or "dapm" in lowered:
        return "asoc_topology"
    if "soc" in lowered or "snd_soc" in lowered or "asoc" in lowered:
        return "asoc_core"
    if "clk" in lowered or "regulator" in lowered or "gpio" in lowered:
        return "platform_power"
    return "audio_runtime"


def _dedupe_sorted(values: list[Any]) -> list[str]:
    return sorted({str(item).strip() for item in values if str(item).strip()})


def build_subsystem_boundary_map(
    *,
    target_id: str,
    driver_registration_graph: Mapping[str, Any],
    callback_chain_graph: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    subsystem_descriptor: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> SubsystemBoundaryResult:
    registration = _as_dict(driver_registration_graph)
    callbacks = _as_dict(callback_chain_graph)
    topology = _as_dict(topology_runtime_graph)
    descriptors = _as_dict(subsystem_descriptor)

    component_lifecycle = _as_list(registration.get("component_lifecycle"))
    ops_lifecycle = _as_list(registration.get("ops_lifecycle"))
    callback_nodes = [
        row for row in _as_list(callbacks.get("nodes")) if isinstance(row, dict) and str(row.get("kind", "")) == "callback_function"
    ]
    topology_nodes = [row for row in _as_list(topology.get("nodes")) if isinstance(row, dict)]

    boundaries: dict[str, dict[str, Any]] = {}

    def _append(subsystem: str, construct: str) -> None:
        key = subsystem.strip() or "audio_runtime"
        record = boundaries.setdefault(
            key,
            {
                "subsystem": key,
                "constructs": [],
                "ownership": "maintainer_review_required",
            },
        )
        record["constructs"].append(construct)

    for row in component_lifecycle:
        item = _as_dict(row)
        name = str(item.get("component_driver", "")).strip()
        if not name:
            continue
        _append(_classify_subsystem(name), name)

    for row in ops_lifecycle:
        item = _as_dict(row)
        name = str(item.get("ops_structure", "")).strip()
        if name:
            _append(_classify_subsystem(name), name)
        for cb in _as_list(item.get("callbacks")):
            cb_name = str(_as_dict(cb).get("function", "")).strip()
            if cb_name:
                _append(_classify_subsystem(cb_name), cb_name)

    for row in callback_nodes:
        ident = str(row.get("id", "")).strip()
        if ident:
            _append(_classify_subsystem(ident), ident)

    for row in topology_nodes:
        ident = str(row.get("id", "")).strip()
        if ident:
            _append(_classify_subsystem(ident), ident)

    descriptor_map = _as_dict(descriptors.get("descriptors"))
    for subsystem, record in boundaries.items():
        if subsystem in descriptor_map:
            record["ownership"] = str(_as_dict(descriptor_map.get(subsystem)).get("owner", "maintainer_review_required"))
        record["constructs"] = _dedupe_sorted(record["constructs"])[:600]
        record["construct_count"] = len(record["constructs"])

    crossings: list[dict[str, Any]] = []
    boundary_items = sorted(boundaries.values(), key=lambda row: str(row.get("subsystem", "")))
    subsystems = [str(row.get("subsystem", "")) for row in boundary_items if str(row.get("subsystem", ""))]

    for source in subsystems:
        for target in subsystems:
            if source >= target:
                continue
            source_count = int(_as_dict(boundaries.get(source)).get("construct_count", 0) or 0)
            target_count = int(_as_dict(boundaries.get(target)).get("construct_count", 0) or 0)
            if source_count == 0 or target_count == 0:
                continue
            if {source, target} <= {"asoc_core", "asoc_topology", "audio_runtime"}:
                risk = "LOW"
            elif "dsp" in {source, target} or "soundwire" in {source, target}:
                risk = "HIGH"
            else:
                risk = "MEDIUM"
            crossings.append(
                {
                    "from": source,
                    "to": target,
                    "risk": risk,
                    "maintainer_split_recommended": risk in {"HIGH", "MEDIUM"},
                }
            )

    high_risk_crossings = len([row for row in crossings if str(row.get("risk", "")) == "HIGH"])
    total_subsystems = max(1, len(boundary_items))
    boundary_confidence = round(max(0.0, min(1.0, 1.0 - 0.08 * high_risk_crossings - 0.02 * (total_subsystems - 1))), 3)

    classification = "PASS"
    if high_risk_crossings > 4:
        classification = "FAIL_CLOSED"
    elif high_risk_crossings > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "subsystem_boundary_map",
        "target_id": str(target_id),
        "classification": classification,
        "boundary_confidence": boundary_confidence,
        "subsystems": boundary_items,
        "cross_subsystem_dependencies": sorted(
            crossings,
            key=lambda row: (str(row.get("from", "")), str(row.get("to", ""))),
        ),
        "summary": {
            "subsystem_count": len(boundary_items),
            "high_risk_crossings": high_risk_crossings,
            "maintainership_split_required": high_risk_crossings > 0,
        },
        "adapter_hints": {
            "provider": str(descriptors.get("provider", "")),
            "fingerprint": str(descriptors.get("fingerprint", "")),
        },
        "advisory_only_behavior": True,
        "runtime_truth_precedence": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SubsystemBoundaryResult(
        subsystem_boundary_map=payload,
        boundary_confidence=boundary_confidence,
        deterministic_fingerprint=fingerprint,
    )
