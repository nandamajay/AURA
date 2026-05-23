"""Runtime-aware patch correlation and blast-radius estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimePatchCorrelationResult:
    runtime_patch_correlation: dict[str, Any]
    runtime_alignment_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in markers)


def correlate_runtime_patch_impact(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    runtime_source_correlation: Mapping[str, Any],
    patch_dependency_graph: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RuntimePatchCorrelationResult:
    runtime = _as_dict(runtime_evidence)
    source = _as_dict(runtime_source_correlation)
    dependency_graph = _as_dict(patch_dependency_graph)
    topology = _as_dict(topology_runtime_graph)

    command_rows = [row for row in _as_list(source.get("command_source_correlations")) if isinstance(row, dict)]
    patch_nodes = [row for row in _as_list(dependency_graph.get("nodes")) if isinstance(row, dict)]

    mapped_impacts: list[dict[str, Any]] = []
    impacted_patches: set[str] = set()

    for row in command_rows:
        command = str(row.get("runtime_command", "")).strip()
        files = [str(item) for item in _as_list(row.get("matched_source_files")) if str(item).strip()]
        confidence = float(row.get("correlation_confidence", 0.0) or 0.0)

        command_scope: list[str] = []
        if _contains_any(command, ("amixer", "mixer", "dapm")):
            command_scope.append("patch_02_topology_fe_be_normalization")
            command_scope.append("patch_06_runtime_correlation_guardrails")
        if _contains_any(command, ("push", "aplay", "pcm", "multimedia", "dai")):
            command_scope.append("patch_06_runtime_correlation_guardrails")
            command_scope.append("patch_08_bisectability_and_series_finalize")
        if _contains_any(" ".join(files), ("soundwire", "swr")):
            command_scope.append("patch_05_soundwire_and_dsp_decoupling")
        if _contains_any(" ".join(files), ("dsp", "apr", "adsp", "qdsp")):
            command_scope.append("patch_05_soundwire_and_dsp_decoupling")
            command_scope.append("patch_04_vendor_contamination_isolation")

        command_scope = sorted({item for item in command_scope if item})
        for patch_id in command_scope:
            impacted_patches.add(patch_id)

        mapped_impacts.append(
            {
                "runtime_command": command,
                "correlation_confidence": round(confidence, 3),
                "matched_source_files": files[:120],
                "impacted_patch_nodes": command_scope,
            }
        )

    declared_patch_ids = {str(row.get("patch_id", "")).strip() for row in patch_nodes if str(row.get("patch_id", "")).strip()}
    impacted_known = sorted([item for item in impacted_patches if item in declared_patch_ids])

    coverage = round(len(impacted_known) / max(1, len(declared_patch_ids)), 3)
    avg_corr = round(
        sum(float(_as_dict(row).get("correlation_confidence", 0.0) or 0.0) for row in mapped_impacts)
        / max(1, len(mapped_impacts)),
        3,
    )

    runtime_success = bool(runtime.get("process_success", False)) and bool(runtime.get("playback_completion", False))
    topology_edges = len(_as_list(topology.get("edges")))

    runtime_alignment_score = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * coverage + 0.35 * avg_corr + 0.15 * (1.0 if runtime_success else 0.0) + 0.05 * min(1.0, topology_edges / 20.0),
            ),
        ),
        3,
    )

    if runtime_alignment_score < 0.35:
        blast_radius = "HIGH"
    elif runtime_alignment_score < 0.65:
        blast_radius = "MEDIUM"
    else:
        blast_radius = "LOW"

    classification = "PASS"
    if blast_radius == "HIGH":
        classification = "FAIL_CLOSED"
    elif blast_radius == "MEDIUM":
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_patch_correlation",
        "target_id": str(target_id),
        "classification": classification,
        "runtime_alignment_score": runtime_alignment_score,
        "regression_blast_radius": blast_radius,
        "summary": {
            "mapped_command_count": len(mapped_impacts),
            "impacted_patch_count": len(impacted_known),
            "declared_patch_count": len(declared_patch_ids),
            "coverage": coverage,
            "average_runtime_source_correlation": avg_corr,
        },
        "command_patch_mappings": mapped_impacts[:500],
        "runtime_state": {
            "process_success": bool(runtime.get("process_success", False)),
            "playback_completion": bool(runtime.get("playback_completion", False)),
            "route_fingerprint": str(runtime.get("route_fingerprint", "")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimePatchCorrelationResult(
        runtime_patch_correlation=payload,
        runtime_alignment_score=runtime_alignment_score,
        deterministic_fingerprint=fingerprint,
    )
