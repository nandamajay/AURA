"""Runtime hardware truth graph reconstruction from normalized traces."""

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


def _msg(row: Mapping[str, Any]) -> str:
    return str(_as_dict(row).get("message", "")).strip()


def _domain(row: Mapping[str, Any]) -> str:
    return str(_as_dict(row).get("domain", "GENERIC")).upper()


def _contains(row: Mapping[str, Any], token: str) -> bool:
    return token.lower() in _msg(row).lower()


def _event_sig(row: Mapping[str, Any]) -> dict[str, Any]:
    item = _as_dict(row)
    return {
        "event_id": str(item.get("event_id", "")),
        "source": str(item.get("source", "")),
        "timestamp_ms": _to_float(item.get("timestamp_ms"), 0.0),
        "domain": str(item.get("domain", "GENERIC")),
        "message": str(item.get("message", "")),
    }


@dataclass(frozen=True)
class RuntimeHardwareTruthGraphResult:
    hardware_truth_graph: dict[str, Any]
    ipc_topology_map: dict[str, Any]
    runtime_path_graph: dict[str, Any]


class RuntimeHardwareTruthGraphBuilder:
    """Build portable runtime topology cognition from normalized events."""

    def build(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        normalized_events: list[Mapping[str, Any]],
        evidence_references: list[str] | None,
    ) -> RuntimeHardwareTruthGraphResult:
        rows = [_as_dict(item) for item in normalized_events if isinstance(item, Mapping)]
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        pcm_events = [row for row in rows if _domain(row) == "PCM" or _contains(row, "pcm")]
        dapm_events = [row for row in rows if _domain(row) == "DAPM" or _contains(row, "dapm")]
        swr_events = [row for row in rows if _domain(row) == "SOUNDWIRE" or _contains(row, "soundwire") or _contains(row, "swr")]
        dsp_events = [row for row in rows if _domain(row) == "DSP" or _contains(row, "mailbox") or _contains(row, "dsp")]
        irq_events = [row for row in rows if _domain(row) == "IRQ" or _contains(row, "irq")]
        clock_events = [row for row in rows if _domain(row) == "CLOCK" or _contains(row, "clock") or _contains(row, "clk")]
        regulator_events = [row for row in rows if _domain(row) == "REGULATOR" or _contains(row, "regulator")]

        fe_be_edges: list[dict[str, Any]] = []
        swr_links: list[dict[str, Any]] = []
        codec_links: list[dict[str, Any]] = []
        mailbox_links: list[dict[str, Any]] = []

        for row in rows:
            fe = str(row.get("fe_reference", "")).strip()
            be = str(row.get("be_reference", "")).strip()
            message = _msg(row)
            if fe and be:
                fe_be_edges.append(
                    {
                        "from": fe,
                        "to": be,
                        "edge_type": "fe_be_runtime_link",
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                        "evidence": message,
                    }
                )
            if "soundwire" in message.lower() or "swr" in message.lower():
                swr_links.append(
                    {
                        "node": message,
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                        "edge_type": "soundwire_activation",
                    }
                )
            if "codec" in message.lower() or "wsa" in message.lower() or "wcd" in message.lower():
                codec_links.append(
                    {
                        "codec_event": message,
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                    }
                )
            if "mailbox" in message.lower() or "apr" in message.lower():
                mailbox_links.append(
                    {
                        "mailbox_event": message,
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                    }
                )

        pcm_lifecycle = [
            {
                "step_index": idx,
                "message": _msg(row),
                "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                "fe_reference": str(row.get("fe_reference", "")),
                "be_reference": str(row.get("be_reference", "")),
            }
            for idx, row in enumerate(sorted(pcm_events, key=lambda item: _to_float(item.get("timestamp_ms"), 0.0)), start=1)
        ]

        dapm_edges = [
            {
                "message": _msg(row),
                "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                "edge_type": "dapm_route",
            }
            for row in sorted(dapm_events, key=lambda item: _to_float(item.get("timestamp_ms"), 0.0))
        ]

        irq_ordering = [
            {
                "irq_reference": str(row.get("irq_reference", "")),
                "message": _msg(row),
                "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                "order": idx,
            }
            for idx, row in enumerate(sorted(irq_events, key=lambda item: _to_float(item.get("timestamp_ms"), 0.0)), start=1)
        ]

        hardware_fail_reasons: list[str] = []
        if not pcm_lifecycle:
            hardware_fail_reasons.append("pcm_lifecycle_unproven")
        if not fe_be_edges:
            hardware_fail_reasons.append("fe_be_runtime_links_missing")
        if not mailbox_links:
            hardware_fail_reasons.append("mailbox_sync_unproven")

        hardware_truth_graph = {
            "schema_version": "1.0",
            "report_name": "hardware_truth_graph",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "FAIL_CLOSED" if hardware_fail_reasons else "PASS",
            "fail_closed_reasons": hardware_fail_reasons,
            "nodes": {
                "pcm_lifecycle": pcm_lifecycle,
                "dapm_routes": dapm_edges,
                "soundwire_links": swr_links,
                "codec_relationships": codec_links,
                "dsp_events": [_event_sig(row) for row in dsp_events],
                "irq_ordering": irq_ordering,
                "clock_sequence": [_event_sig(row) for row in clock_events],
                "regulator_sequence": [_event_sig(row) for row in regulator_events],
                "mailbox_synchronization": mailbox_links,
                "fe_be_links": fe_be_edges,
            },
            "summary": {
                "event_count": len(rows),
                "pcm_event_count": len(pcm_events),
                "dapm_event_count": len(dapm_events),
                "soundwire_event_count": len(swr_events),
                "dsp_event_count": len(dsp_events),
                "irq_event_count": len(irq_events),
                "clock_event_count": len(clock_events),
                "regulator_event_count": len(regulator_events),
                "fe_be_link_count": len(fe_be_edges),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        hardware_truth_graph["deterministic_fingerprint"] = stable_fingerprint(
            {
                "classification": hardware_truth_graph["classification"],
                "fail_closed_reasons": hardware_truth_graph["fail_closed_reasons"],
                "nodes": hardware_truth_graph["nodes"],
            }
        )

        ipc_topology_map = {
            "schema_version": "1.0",
            "report_name": "ipc_topology_map",
            "target_id": str(target_id),
            "classification": "PASS" if mailbox_links else "FAIL_CLOSED",
            "ipc_channels": mailbox_links,
            "dsp_sync_chain": [_event_sig(row) for row in dsp_events],
            "summary": {
                "ipc_event_count": len(mailbox_links),
                "dsp_sync_count": len(dsp_events),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        ipc_topology_map["deterministic_fingerprint"] = stable_fingerprint(ipc_topology_map)

        path_edges: list[dict[str, Any]] = []
        for row in pcm_lifecycle:
            fe = str(row.get("fe_reference", ""))
            be = str(row.get("be_reference", ""))
            if fe and be:
                path_edges.append(
                    {
                        "from": fe,
                        "to": be,
                        "path_type": "pcm_runtime_path",
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                    }
                )
        for row in dapm_edges:
            path_edges.append(
                {
                    "from": "DAPM",
                    "to": "ROUTE",
                    "path_type": "dapm_runtime_path",
                    "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                    "message": str(row.get("message", "")),
                }
            )

        runtime_path_graph = {
            "schema_version": "1.0",
            "report_name": "runtime_path_graph",
            "target_id": str(target_id),
            "classification": "PASS" if path_edges else "FAIL_CLOSED",
            "edges": path_edges,
            "summary": {
                "path_edge_count": len(path_edges),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_path_graph["deterministic_fingerprint"] = stable_fingerprint(runtime_path_graph)

        return RuntimeHardwareTruthGraphResult(
            hardware_truth_graph=hardware_truth_graph,
            ipc_topology_map=ipc_topology_map,
            runtime_path_graph=runtime_path_graph,
        )
