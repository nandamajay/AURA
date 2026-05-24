"""Deterministic runtime fingerprint and replay artifact generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sorted_events(events: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [_as_dict(row) for row in events if isinstance(row, Mapping)]
    rows.sort(
        key=lambda row: (
            _to_float(row.get("timestamp_ms"), 0.0),
            str(row.get("source", "")),
            str(row.get("event_id", "")),
        )
    )
    return rows


def _sig_list(rows: list[Mapping[str, Any]], predicate) -> list[str]:
    out: list[str] = []
    for row in rows:
        item = _as_dict(row)
        if not predicate(item):
            continue
        out.append(str(item.get("message", "")).strip().lower())
    return out


@dataclass(frozen=True)
class RuntimeFingerprintResult:
    runtime_equivalence_fingerprint: dict[str, Any]
    deterministic_runtime_replay: dict[str, Any]


class RuntimeFingerprintEngine:
    """Build replay-safe runtime fingerprints for equivalence governance."""

    def build(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        normalized_events: list[Mapping[str, Any]],
        hardware_truth_graph: Mapping[str, Any],
        divergence_report: Mapping[str, Any],
        confidence_report: Mapping[str, Any],
        evidence_references: list[str] | None,
    ) -> RuntimeFingerprintResult:
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]
        rows = _sorted_events(normalized_events)
        truth_graph = _as_dict(hardware_truth_graph)

        pcm_order = _sig_list(rows, lambda row: str(row.get("domain", "")).upper() == "PCM")
        irq_order = _sig_list(rows, lambda row: str(row.get("domain", "")).upper() == "IRQ")
        dsp_order = _sig_list(rows, lambda row: str(row.get("domain", "")).upper() == "DSP")
        clock_order = _sig_list(rows, lambda row: str(row.get("domain", "")).upper() == "CLOCK")
        regulator_order = _sig_list(rows, lambda row: str(row.get("domain", "")).upper() == "REGULATOR")

        fe_be_order: list[str] = []
        for row in rows:
            fe = str(_as_dict(row).get("fe_reference", "")).strip()
            be = str(_as_dict(row).get("be_reference", "")).strip()
            if fe and be:
                fe_be_order.append(f"{fe}->{be}")

        soundwire_graph = [
            str(_as_dict(item).get("node", _as_dict(item).get("message", ""))).strip().lower()
            for item in _as_list(_as_dict(truth_graph.get("nodes")).get("soundwire_links"))
            if str(_as_dict(item).get("node", _as_dict(item).get("message", ""))).strip()
        ]

        mailbox_order = [
            str(_as_dict(item).get("mailbox_event", _as_dict(item).get("message", ""))).strip().lower()
            for item in _as_list(_as_dict(truth_graph.get("nodes")).get("mailbox_synchronization"))
            if str(_as_dict(item).get("mailbox_event", _as_dict(item).get("message", ""))).strip()
        ]

        dimensions = {
            "pcm_lifecycle_order": pcm_order,
            "irq_sequence": irq_order,
            "dsp_sync_order": dsp_order,
            "clock_activation_order": clock_order,
            "regulator_enable_order": regulator_order,
            "backend_frontend_routing": fe_be_order,
            "soundwire_activation_graph": soundwire_graph,
            "mailbox_sync_sequence": mailbox_order,
        }

        dimension_fingerprints = {
            key: stable_fingerprint({"values": values}) for key, values in sorted(dimensions.items())
        }

        runtime_equivalence_fingerprint = {
            "schema_version": "1.0",
            "report_name": "runtime_equivalence_fingerprint",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "dimensions": dimensions,
            "dimension_fingerprints": dimension_fingerprints,
            "summary": {
                "dimension_count": len(dimensions),
                "event_count": len(rows),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_equivalence_fingerprint["deterministic_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "dimension_fingerprints": dimension_fingerprints,
            }
        )

        deterministic_runtime_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_runtime_replay",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "PASS",
            "replay_signal": {
                "deterministic_event_ordering": True,
                "event_count": len(rows),
                "fingerprint": str(runtime_equivalence_fingerprint.get("deterministic_fingerprint", "")),
            },
            "artifact_lineage": {
                "runtime_equivalence_fingerprint": str(runtime_equivalence_fingerprint.get("deterministic_fingerprint", "")),
                "runtime_divergence_report": str(_as_dict(divergence_report).get("deterministic_fingerprint", "")),
                "runtime_confidence_report": str(_as_dict(confidence_report).get("deterministic_fingerprint", "")),
                "hardware_truth_graph": str(_as_dict(hardware_truth_graph).get("deterministic_fingerprint", "")),
            },
            "event_digest": [
                {
                    "index": idx,
                    "event_id": str(_as_dict(row).get("event_id", "")),
                    "timestamp_ms": _to_float(_as_dict(row).get("timestamp_ms"), 0.0),
                    "domain": str(_as_dict(row).get("domain", "")),
                    "message": str(_as_dict(row).get("message", "")),
                }
                for idx, row in enumerate(rows[:200], start=1)
            ],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_runtime_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_runtime_replay)

        return RuntimeFingerprintResult(
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            deterministic_runtime_replay=deterministic_runtime_replay,
        )
