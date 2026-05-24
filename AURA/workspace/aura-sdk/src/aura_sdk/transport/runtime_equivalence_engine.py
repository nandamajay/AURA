"""Runtime equivalence cognition between baseline and transformed traces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_CRITICAL_DIMENSIONS = {
    "irq_divergence",
    "dsp_sequence_instability",
    "mailbox_ordering_divergence",
    "soundwire_topology_mismatch",
    "pcm_transition_inconsistency",
    "runtime_sensitive_region_instability",
}


@dataclass(frozen=True)
class RuntimeEquivalenceResult:
    runtime_equivalence_report: dict[str, Any]
    runtime_divergence_report: dict[str, Any]
    runtime_confidence_report: dict[str, Any]


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


def _event_signature(events: list[Mapping[str, Any]], *, domain: str | None = None) -> list[str]:
    rows: list[str] = []
    for row in events:
        item = _as_dict(row)
        row_domain = str(item.get("domain", "")).upper()
        if domain and row_domain != domain.upper():
            continue
        rows.append(f"{row_domain}:{str(item.get('message', '')).strip().lower()}")
    return rows


def _graph_signature(graph: Mapping[str, Any], key: str) -> list[str]:
    payload = _as_dict(_as_dict(graph).get("nodes")).get(key)
    out: list[str] = []
    for row in _as_list(payload):
        item = _as_dict(row)
        msg = str(item.get("message", item.get("mailbox_event", item.get("codec_event", "")))).strip().lower()
        if msg:
            out.append(msg)
    return out


def _dim_diff_count(base: list[str], transformed: list[str]) -> tuple[int, list[str], list[str]]:
    base_set = set(base)
    transformed_set = set(transformed)
    missing = sorted(base_set - transformed_set)
    added = sorted(transformed_set - base_set)
    return len(missing) + len(added), missing, added


class RuntimeEquivalenceEngine:
    """Compare baseline vs transformed runtime behavior with fail-closed scoring."""

    def evaluate(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        baseline_events: list[Mapping[str, Any]],
        transformed_events: list[Mapping[str, Any]],
        baseline_truth_graph: Mapping[str, Any],
        transformed_truth_graph: Mapping[str, Any],
        evidence_references: list[str] | None,
    ) -> RuntimeEquivalenceResult:
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        base_events = [_as_dict(row) for row in baseline_events if isinstance(row, Mapping)]
        tx_events = [_as_dict(row) for row in transformed_events if isinstance(row, Mapping)]
        base_graph = _as_dict(baseline_truth_graph)
        tx_graph = _as_dict(transformed_truth_graph)

        base_irq = _event_signature(base_events, domain="IRQ")
        tx_irq = _event_signature(tx_events, domain="IRQ")
        base_pcm = _event_signature(base_events, domain="PCM")
        tx_pcm = _event_signature(tx_events, domain="PCM")
        base_swr = _event_signature(base_events, domain="SOUNDWIRE")
        tx_swr = _event_signature(tx_events, domain="SOUNDWIRE")
        base_clk = _event_signature(base_events, domain="CLOCK")
        tx_clk = _event_signature(tx_events, domain="CLOCK")
        base_dsp = _event_signature(base_events, domain="DSP")
        tx_dsp = _event_signature(tx_events, domain="DSP")

        base_mailbox = _graph_signature(base_graph, "mailbox_synchronization")
        tx_mailbox = _graph_signature(tx_graph, "mailbox_synchronization")

        dimensions: list[dict[str, Any]] = []

        def add_dimension(name: str, base: list[str], tx: list[str], weight: float, critical: bool) -> None:
            diff_count, missing, added = _dim_diff_count(base, tx)
            max_items = max(len(set(base)), len(set(tx)), 1)
            drift_ratio = round(diff_count / max_items, 6)
            dimensions.append(
                {
                    "dimension": name,
                    "weight": weight,
                    "critical": critical,
                    "baseline_count": len(base),
                    "transformed_count": len(tx),
                    "difference_count": diff_count,
                    "drift_ratio": drift_ratio,
                    "missing_items": missing[:30],
                    "added_items": added[:30],
                    "classification": "DIVERGED" if diff_count > 0 else "EQUIVALENT",
                }
            )

        add_dimension("irq_divergence", base_irq, tx_irq, 0.14, True)
        add_dimension("lifecycle_drift", base_pcm, tx_pcm, 0.15, False)
        add_dimension("clock_mismatch", base_clk, tx_clk, 0.08, False)
        add_dimension("dsp_sequence_instability", base_dsp, tx_dsp, 0.14, True)
        add_dimension("mailbox_ordering_divergence", base_mailbox, tx_mailbox, 0.15, True)
        add_dimension("soundwire_topology_mismatch", base_swr, tx_swr, 0.11, True)
        add_dimension("pcm_transition_inconsistency", base_pcm, tx_pcm, 0.11, True)

        runtime_sensitive_diff = sum(
            1
            for row in tx_events
            if bool(_as_dict(row).get("runtime_sensitive", False))
            and "delayed" in str(_as_dict(row).get("message", "")).lower()
        )
        dimensions.append(
            {
                "dimension": "runtime_sensitive_region_instability",
                "weight": 0.12,
                "critical": True,
                "baseline_count": 0,
                "transformed_count": runtime_sensitive_diff,
                "difference_count": runtime_sensitive_diff,
                "drift_ratio": 1.0 if runtime_sensitive_diff else 0.0,
                "missing_items": [],
                "added_items": ["runtime_sensitive_delay_detected"] if runtime_sensitive_diff else [],
                "classification": "DIVERGED" if runtime_sensitive_diff else "EQUIVALENT",
            }
        )

        weighted_penalty = 0.0
        critical_divergences: list[str] = []
        total_differences = 0
        for row in dimensions:
            item = _as_dict(row)
            drift = _to_float(item.get("drift_ratio"), 0.0)
            weight = _to_float(item.get("weight"), 0.0)
            weighted_penalty += drift * weight
            total_differences += int(item.get("difference_count", 0))
            if bool(item.get("critical", False)) and str(item.get("classification", "")) == "DIVERGED":
                critical_divergences.append(str(item.get("dimension", "")))

        confidence_score = max(0.0, round(1.0 - weighted_penalty, 6))
        divergence_classification = "PASS" if total_differences == 0 else "FAIL_CLOSED"

        divergence_reasons: list[str] = []
        if total_differences > 0:
            divergence_reasons.append("runtime_divergence_detected")
        if critical_divergences:
            divergence_reasons.append("runtime_sensitive_region_instability")

        runtime_equivalence_report = {
            "schema_version": "1.0",
            "report_name": "runtime_equivalence_report",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "PASS" if total_differences == 0 else "FAIL_CLOSED",
            "summary": {
                "total_differences": total_differences,
                "critical_divergence_count": len(critical_divergences),
                "confidence_score": confidence_score,
            },
            "dimensions": dimensions,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_equivalence_report["deterministic_fingerprint"] = stable_fingerprint(runtime_equivalence_report)

        runtime_divergence_report = {
            "schema_version": "1.0",
            "report_name": "runtime_divergence_report",
            "target_id": str(target_id),
            "classification": divergence_classification,
            "reasons": divergence_reasons,
            "critical_divergences": sorted(set(critical_divergences)),
            "diverged_dimensions": [
                str(_as_dict(row).get("dimension", ""))
                for row in dimensions
                if str(_as_dict(row).get("classification", "")) == "DIVERGED"
            ],
            "summary": {
                "diverged_dimension_count": sum(
                    1 for row in dimensions if str(_as_dict(row).get("classification", "")) == "DIVERGED"
                ),
                "critical_divergence_count": len(critical_divergences),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_divergence_report["deterministic_fingerprint"] = stable_fingerprint(runtime_divergence_report)

        fail_reasons: list[str] = []
        if confidence_score < 0.75:
            fail_reasons.append("runtime_confidence_below_threshold")
        if critical_divergences:
            fail_reasons.append("critical_runtime_divergence_detected")

        runtime_confidence_report = {
            "schema_version": "1.0",
            "report_name": "runtime_confidence_report",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "confidence_score": confidence_score,
            "confidence_threshold": 0.75,
            "fail_closed_reasons": fail_reasons,
            "critical_divergences": sorted(set(critical_divergences)),
            "weights": {str(_as_dict(row).get("dimension", "")): _to_float(_as_dict(row).get("weight"), 0.0) for row in dimensions},
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_confidence_report["deterministic_fingerprint"] = stable_fingerprint(runtime_confidence_report)

        return RuntimeEquivalenceResult(
            runtime_equivalence_report=runtime_equivalence_report,
            runtime_divergence_report=runtime_divergence_report,
            runtime_confidence_report=runtime_confidence_report,
        )
