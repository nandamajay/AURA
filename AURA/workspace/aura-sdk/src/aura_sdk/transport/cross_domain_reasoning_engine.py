"""Cross-domain reasoning over runtime/topology/semantic/migration/patch evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class CrossDomainReasoningResult:
    cross_domain_reasoning: dict[str, Any]
    reasoning_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def build_cross_domain_reasoning(
    *,
    target_id: str,
    runtime_topology_correlation: Mapping[str, Any],
    lifecycle_causality_map: Mapping[str, Any],
    migration_runtime_alignment: Mapping[str, Any],
    patch_runtime_lineage: Mapping[str, Any],
    dsp_runtime_causality_report: Mapping[str, Any],
    upstream_readiness_report: Mapping[str, Any],
    runtime_confidence_score: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> CrossDomainReasoningResult:
    topo = _as_dict(runtime_topology_correlation)
    lifecycle = _as_dict(lifecycle_causality_map)
    migration = _as_dict(migration_runtime_alignment)
    patch = _as_dict(patch_runtime_lineage)
    dsp = _as_dict(dsp_runtime_causality_report)
    readiness = _as_dict(upstream_readiness_report)
    runtime_conf = _as_dict(runtime_confidence_score)

    topo_score = float(topo.get("correlation_score", 0.0) or 0.0)
    lifecycle_score = float(lifecycle.get("causality_score", 0.0) or 0.0)
    migration_score = float(migration.get("alignment_score", 0.0) or 0.0)
    patch_score = float(patch.get("lineage_score", 0.0) or 0.0)
    dsp_score = float(dsp.get("causality_score", 0.0) or 0.0)
    readiness_score = float(readiness.get("readiness_score", 0.0) or 0.0)
    runtime_score = float(runtime_conf.get("runtime_confidence", 0.0) or 0.0)

    reasoning_chains = [
        {
            "chain": "topology_to_runtime",
            "from": "topology_structures",
            "via": "runtime_topology_correlation",
            "to": "runtime_confidence",
            "score": round((topo_score + runtime_score) / 2.0, 3),
        },
        {
            "chain": "runtime_to_migration",
            "from": "runtime_drift",
            "via": "migration_runtime_alignment",
            "to": "migration_governance",
            "score": round(migration_score, 3),
        },
        {
            "chain": "patch_to_runtime",
            "from": "patch_evolution",
            "via": "patch_runtime_lineage",
            "to": "runtime_drift",
            "score": round(patch_score, 3),
        },
        {
            "chain": "dsp_irq_soundwire",
            "from": "dsp_sync",
            "via": "dsp_runtime_causality",
            "to": "irq_soundwire_timing",
            "score": round(dsp_score, 3),
        },
        {
            "chain": "runtime_to_upstream_equivalence",
            "from": "runtime_truth",
            "via": "cross_domain_reasoning",
            "to": "upstream_readiness",
            "score": round((runtime_score + readiness_score) / 2.0, 3),
        },
        {
            "chain": "lifecycle_causality",
            "from": "fe_be_lifecycle",
            "via": "lifecycle_causality_map",
            "to": "regression_localization",
            "score": round(lifecycle_score, 3),
        },
    ]

    reasoning_score = round(
        max(
            0.0,
            min(
                1.0,
                0.18 * topo_score
                + 0.16 * lifecycle_score
                + 0.14 * migration_score
                + 0.14 * patch_score
                + 0.14 * dsp_score
                + 0.12 * readiness_score
                + 0.12 * runtime_score,
            ),
        ),
        3,
    )

    classification = "PASS"
    if any(str(_as_dict(item).get("score", 1.0)) == "0.0" for item in reasoning_chains):
        classification = "ADVISORY_ONLY"
    if reasoning_score < 0.45:
        classification = "FAIL_CLOSED"
    elif reasoning_score < 0.70:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "cross_domain_reasoning",
        "target_id": str(target_id),
        "classification": classification,
        "reasoning_score": reasoning_score,
        "reasoning_chains": reasoning_chains,
        "summary": {
            "topology_runtime_score": round(topo_score, 3),
            "lifecycle_score": round(lifecycle_score, 3),
            "migration_alignment_score": round(migration_score, 3),
            "patch_runtime_score": round(patch_score, 3),
            "dsp_causality_score": round(dsp_score, 3),
            "runtime_confidence": round(runtime_score, 3),
            "upstream_readiness": round(readiness_score, 3),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return CrossDomainReasoningResult(
        cross_domain_reasoning=payload,
        reasoning_score=reasoning_score,
        deterministic_fingerprint=fingerprint,
    )
