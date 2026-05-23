"""Runtime Evidence Acquisition and Hardware Truth Validation layer.

Ingests live-target runtime traces (or archived capture payloads), correlates
them with translation/runtime expectations, and emits deterministic,
replay-safe hardware truth artifacts under fail-closed governance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.debugfs_runtime_ingestor import ingest_debugfs_runtime
from aura_sdk.transport.dmesg_ingestor import ingest_dmesg
from aura_sdk.transport.dsp_mailbox_ingestor import ingest_dsp_mailbox
from aura_sdk.transport.ftrace_ingestor import ingest_ftrace
from aura_sdk.transport.irq_runtime_ingestor import ingest_irq_runtime
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.procfs_runtime_ingestor import ingest_procfs_runtime
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.soundwire_runtime_ingestor import ingest_soundwire_runtime
from aura_sdk.transport.tinymix_state_ingestor import ingest_tinymix_state
from aura_sdk.transport.tracecmd_ingestor import ingest_tracecmd


_REQUIRED_SOURCES = [
    "dmesg",
    "ftrace",
    "trace_cmd",
    "tinymix_state",
    "procfs_runtime",
    "debugfs_runtime",
    "soundwire_runtime",
    "dsp_mailbox",
    "irq_runtime",
    "clocks",
    "regulators",
    "ipc_path",
]

_AUTONOMOUS_POLICY_FLAGS = [
    "autonomous_patching_allowed",
    "autonomous_topology_rewrite_allowed",
    "autonomous_runtime_mutation_allowed",
    "autonomous_upstream_generation_allowed",
]

_FE_RE = re.compile(r"\b(?:fe|frontend|multimedia)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)
_BE_RE = re.compile(r"\b(?:be|backend|rx|tx)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RuntimeEvidenceAcquisitionResult:
    acquisition_bundle: dict[str, Any]


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
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "ok",
            "pass",
            "success",
            "supported",
        }
    return False


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _governance_clean(governance_state: Mapping[str, Any]) -> tuple[bool, list[str]]:
    governance = _as_dict(governance_state)
    reasons: list[str] = []

    if not bool(governance.get("fail_closed_posture", True)):
        reasons.append("fail_closed_posture_disabled")

    for flag in _AUTONOMOUS_POLICY_FLAGS:
        if _is_true(governance.get(flag, False)):
            reasons.append(f"governance_violation:{flag}")

    return (len(reasons) == 0, reasons)


def _timestamp_ms(value: Any, fallback_ms: float) -> float:
    ts = _to_float(value, fallback_ms)
    if ts < 0:
        return round(fallback_ms, 3)
    if ts < 10_000:
        return round(ts * 1000.0, 3)
    return round(ts, 3)


def _event_domain(event_type: str, message: str, source_key: str) -> str:
    text = f"{event_type} {message} {source_key}".lower()
    if any(token in text for token in ("pcm", "dpcm", "aplay", "prepare", "start", "stop", "close", "drain")):
        return "PCM"
    if any(token in text for token in ("dapm", "widget", "route", "power_up", "power_down")):
        return "DAPM"
    if any(token in text for token in ("soundwire", "swr")):
        return "SOUNDWIRE"
    if any(token in text for token in ("mailbox", "adsp", "dsp", "apr")):
        return "DSP"
    if any(token in text for token in ("irq", "interrupt")):
        return "IRQ"
    if any(token in text for token in ("clock", "clk")):
        return "CLOCK"
    if any(token in text for token in ("regulator", "vreg", "ldo")):
        return "REGULATOR"
    if any(token in text for token in ("ipc", "rpmsg", "glink", "smd")):
        return "IPC"
    if any(token in text for token in ("mixer", "tinymix", "amixer")):
        return "MIXER"
    if any(token in text for token in ("proc", "sysfs", "debugfs", "asoc")):
        return "KERNEL_STATE"
    return "GENERIC"


def _extract_fe_ref(text: str) -> str:
    match = _FE_RE.search(text)
    if not match:
        return ""
    return f"FE{match.group(1)}"


def _extract_be_ref(text: str) -> str:
    match = _BE_RE.search(text)
    if not match:
        return ""
    return f"BE{match.group(1)}"


def _ingest_generic_lines(
    *,
    source: str,
    event_type: str,
    payload: Mapping[str, Any],
    default_start_ms: float,
) -> dict[str, Any]:
    lines = [str(item) for item in _as_list(_as_dict(payload).get("lines")) if str(item).strip()]
    events = []
    for idx, line in enumerate(lines, start=1):
        events.append(
            {
                "event_id": f"{source}:{idx}",
                "source": source,
                "timestamp_ms": round(default_start_ms + idx * 4.0, 3),
                "event_type": event_type,
                "message": line.strip(),
                "raw": line,
            }
        )

    out = {
        "schema_version": "1.0",
        "source": source,
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {"event_count": len(events)},
        "read_only_ingestion": True,
    }
    out["deterministic_fingerprint"] = stable_fingerprint(out)
    return out


def _ingest_live_sources(source_payloads: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    payloads = _as_dict(source_payloads)
    ingested = {
        "dmesg": ingest_dmesg(_as_dict(payloads.get("dmesg"))).dmesg_ingestion,
        "ftrace": ingest_ftrace(_as_dict(payloads.get("ftrace"))).ftrace_ingestion,
        "trace_cmd": ingest_tracecmd(_as_dict(payloads.get("trace_cmd"))).tracecmd_ingestion,
        "tinymix_state": ingest_tinymix_state(_as_dict(payloads.get("tinymix_state"))).tinymix_state_ingestion,
        "procfs_runtime": ingest_procfs_runtime(_as_dict(payloads.get("procfs_runtime"))).procfs_runtime_ingestion,
        "debugfs_runtime": ingest_debugfs_runtime(_as_dict(payloads.get("debugfs_runtime"))).debugfs_runtime_ingestion,
        "soundwire_runtime": ingest_soundwire_runtime(_as_dict(payloads.get("soundwire_runtime"))).soundwire_runtime_ingestion,
        "dsp_mailbox": ingest_dsp_mailbox(_as_dict(payloads.get("dsp_mailbox"))).dsp_mailbox_ingestion,
        "irq_runtime": ingest_irq_runtime(_as_dict(payloads.get("irq_runtime"))).irq_runtime_ingestion,
        "clocks": _ingest_generic_lines(
            source="clock_state",
            event_type="clock_state",
            payload=_as_dict(payloads.get("clocks")),
            default_start_ms=1800.0,
        ),
        "regulators": _ingest_generic_lines(
            source="regulator_state",
            event_type="regulator_state",
            payload=_as_dict(payloads.get("regulators")),
            default_start_ms=1900.0,
        ),
        "ipc_path": _ingest_generic_lines(
            source="ipc_path",
            event_type="ipc_path_state",
            payload=_as_dict(payloads.get("ipc_path")),
            default_start_ms=2000.0,
        ),
    }
    return ingested


def _normalize_events(ingested_sources: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw: list[dict[str, Any]] = []
    seq = 0
    for source_key in sorted(ingested_sources.keys()):
        source_payload = _as_dict(ingested_sources.get(source_key))
        for event in _as_list(source_payload.get("events")):
            item = _as_dict(event)
            seq += 1
            message = str(item.get("message", item.get("detail", ""))).strip()
            event_type = str(item.get("event_type", "runtime_event")).strip()
            raw.append(
                {
                    "sequence_index": seq,
                    "event_id": str(item.get("event_id", f"{source_key}:{seq}")),
                    "source_key": source_key,
                    "source": str(item.get("source", source_key)),
                    "timestamp_ms": _timestamp_ms(item.get("timestamp_ms", 1000.0 + seq * 3.0), 1000.0 + seq * 3.0),
                    "event_type": event_type,
                    "message": message,
                    "domain": _event_domain(event_type, message, source_key),
                    "fe_reference": _extract_fe_ref(message),
                    "be_reference": _extract_be_ref(message),
                    "raw": item,
                }
            )

    normalized = sorted(raw, key=lambda row: (float(row.get("timestamp_ms", 0.0)), str(row.get("event_id", ""))))
    for idx, row in enumerate(normalized, start=1):
        row["normalized_index"] = idx
    return raw, normalized


def _build_ipc_topology_map(
    *,
    target_id: str,
    ipcat_descriptor: Mapping[str, Any],
    topology_adapter: Mapping[str, Any],
    normalized_events: list[Mapping[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    descriptor = _as_dict(ipcat_descriptor)
    adapter = _as_dict(topology_adapter)
    topology = _as_dict(adapter.get("topology_cognition"))
    dts = _as_dict(adapter.get("dts_cognition"))

    ipc_events = [
        row
        for row in normalized_events
        if str(_as_dict(row).get("domain", "")) in {"IPC", "DSP"}
    ]

    ipc_nodes = [
        str(item)
        for item in _as_list(descriptor.get("ipc_nodes", descriptor.get("ipc_paths")))
        if str(item).strip()
    ]
    if not ipc_nodes:
        ipc_nodes = ["apr", "rpmsg", "glink"]

    hardware = {
        "platform": str(descriptor.get("platform", descriptor.get("target", target_id))),
        "soc": str(descriptor.get("soc", "")),
        "board": str(descriptor.get("board", "")),
        "audio_subsystem": str(descriptor.get("audio_subsystem", "qcom_audio")),
        "ip_blocks": [
            str(item)
            for item in _as_list(descriptor.get("ip_blocks"))
            if str(item).strip()
        ],
    }

    ipc_map = {
        "schema_version": "1.0",
        "report_name": "ipc_topology_map",
        "target_id": str(target_id),
        "classification": "PASS" if ipc_events else "ADVISORY_ONLY",
        "ipcat_hardware_descriptor": hardware,
        "ipc_nodes": sorted(set(ipc_nodes)),
        "ipc_paths": [
            {
                "path_id": f"ipc_path:{idx}",
                "source": str(_as_dict(event).get("source", "")),
                "message": str(_as_dict(event).get("message", "")),
                "timestamp_ms": _to_float(_as_dict(event).get("timestamp_ms", 0.0), 0.0),
                "domain": str(_as_dict(event).get("domain", "")),
            }
            for idx, event in enumerate(ipc_events, start=1)
        ],
        "topology_awareness": {
            "topology_fingerprint": str(topology.get("topology_fingerprint", "")),
            "dts_fingerprint": str(dts.get("dts_fingerprint", "")),
            "backend_frontend_mappings": _as_list(dts.get("backend_frontend_mappings")),
            "soundwire_topology_markers": _as_list(dts.get("soundwire_topology_markers")),
        },
        "summary": {
            "ipc_event_count": len(ipc_events),
            "ipc_node_count": len(set(ipc_nodes)),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    ipc_map["deterministic_fingerprint"] = stable_fingerprint(ipc_map)
    return ipc_map


def _build_runtime_topology(
    *,
    target_id: str,
    normalized_events: list[Mapping[str, Any]],
    ipc_topology_map: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: set[str] = {f"target:{target_id}"}
    edges: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = {}
    fe_nodes: set[str] = set()
    be_nodes: set[str] = set()

    prev_id = ""
    for event in normalized_events:
        item = _as_dict(event)
        eid = str(item.get("event_id", ""))
        domain = str(item.get("domain", "GENERIC"))
        domain_counts[domain] = int(domain_counts.get(domain, 0)) + 1
        source_node = f"source:{str(item.get('source_key', 'unknown'))}"
        nodes.add(source_node)
        nodes.add(f"domain:{domain}")

        fe = str(item.get("fe_reference", "")).strip()
        if fe:
            fe_nodes.add(fe)
            nodes.add(f"fe:{fe}")
            edges.append({"from": f"domain:{domain}", "to": f"fe:{fe}", "relation": "observed_frontend"})
        be = str(item.get("be_reference", "")).strip()
        if be:
            be_nodes.add(be)
            nodes.add(f"be:{be}")
            edges.append({"from": f"domain:{domain}", "to": f"be:{be}", "relation": "observed_backend"})

        edges.append({"from": source_node, "to": f"domain:{domain}", "relation": "emits"})
        if prev_id:
            edges.append({"from": f"event:{prev_id}", "to": f"event:{eid}", "relation": "runtime_order"})
        nodes.add(f"event:{eid}")
        prev_id = eid

    for fe in sorted(fe_nodes):
        for be in sorted(be_nodes):
            if fe[-1:] == be[-1:]:
                edges.append({"from": f"fe:{fe}", "to": f"be:{be}", "relation": "runtime_fe_be_link"})

    ipc_nodes = [str(item) for item in _as_list(_as_dict(ipc_topology_map).get("ipc_nodes")) if str(item).strip()]
    for node in ipc_nodes:
        nodes.add(f"ipc:{node}")
        edges.append({"from": f"target:{target_id}", "to": f"ipc:{node}", "relation": "ipc_path_available"})

    topology = {
        "schema_version": "1.0",
        "report_name": "hardware_truth_graph",
        "target_id": str(target_id),
        "classification": "PASS" if normalized_events else "FAIL_CLOSED",
        "nodes": [{"id": node} for node in sorted(nodes)],
        "edges": sorted(
            edges,
            key=lambda row: (
                str(_as_dict(row).get("from", "")),
                str(_as_dict(row).get("to", "")),
                str(_as_dict(row).get("relation", "")),
            ),
        ),
        "summary": {
            "event_count": len(normalized_events),
            "domain_counts": {key: domain_counts[key] for key in sorted(domain_counts.keys())},
            "fe_count": len(fe_nodes),
            "be_count": len(be_nodes),
            "ipc_node_count": len(ipc_nodes),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    topology["deterministic_fingerprint"] = stable_fingerprint(topology)
    return topology


def _build_target_runtime_capture(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    ingested_sources: Mapping[str, Any],
    normalized_events: list[Mapping[str, Any]],
    ipc_topology_map: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    capture = {
        "schema_version": "1.0",
        "report_name": "target_runtime_capture",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": "PASS" if normalized_events else "FAIL_CLOSED",
        "ingested_sources": {key: _as_dict(value) for key, value in sorted(_as_dict(ingested_sources).items())},
        "normalized_events": [dict(_as_dict(row)) for row in normalized_events],
        "ipcat_topology_fingerprint": str(_as_dict(ipc_topology_map).get("deterministic_fingerprint", "")),
        "summary": {
            "source_count": len(_as_dict(ingested_sources)),
            "event_count": len(normalized_events),
            "domain_count": len(
                {
                    str(_as_dict(event).get("domain", "GENERIC"))
                    for event in normalized_events
                    if str(_as_dict(event).get("domain", "GENERIC")).strip()
                }
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    capture["deterministic_fingerprint"] = stable_fingerprint(capture)
    return capture


def _build_evidence_quality_report(
    *,
    target_id: str,
    raw_events: list[Mapping[str, Any]],
    normalized_events: list[Mapping[str, Any]],
    ingested_sources: Mapping[str, Any],
    governance_ok: bool,
    evidence_references: list[str],
) -> dict[str, Any]:
    sources = _as_dict(ingested_sources)
    missing_sources = [
        key
        for key in _REQUIRED_SOURCES
        if str(_as_dict(_as_dict(sources).get(key)).get("classification", "MISSING")).upper() == "MISSING"
    ]

    ordering_violations = 0
    prev_ts = None
    for row in raw_events:
        ts = _to_float(_as_dict(row).get("timestamp_ms", 0.0), 0.0)
        if prev_ts is not None and ts < prev_ts:
            ordering_violations += 1
        prev_ts = ts

    integrity_issues = []
    for row in normalized_events:
        item = _as_dict(row)
        if not str(item.get("event_id", "")).strip():
            integrity_issues.append("missing_event_id")
            continue
        if _to_float(item.get("timestamp_ms", -1.0), -1.0) < 0:
            integrity_issues.append("negative_timestamp")
            continue
        if not str(item.get("domain", "")).strip():
            integrity_issues.append("missing_domain")

    coverage = round((len(_REQUIRED_SOURCES) - len(missing_sources)) / max(1, len(_REQUIRED_SOURCES)), 3)
    ordering_score = 0.0 if ordering_violations > 0 else 1.0
    integrity_score = 0.0 if integrity_issues else 1.0
    volume_score = min(1.0, len(normalized_events) / 120.0)

    quality_score = round(
        max(0.0, min(1.0, 0.45 * coverage + 0.20 * ordering_score + 0.20 * integrity_score + 0.15 * volume_score)),
        3,
    )
    classification = "PASS"
    if not governance_ok or ordering_violations > 0 or integrity_issues:
        classification = "FAIL_CLOSED"
    elif quality_score < 0.68:
        classification = "ADVISORY_ONLY"

    report = {
        "schema_version": "1.0",
        "report_name": "evidence_quality_report",
        "target_id": str(target_id),
        "classification": classification,
        "quality_score": quality_score,
        "coverage": {
            "required_sources": list(_REQUIRED_SOURCES),
            "missing_required_sources": missing_sources,
            "coverage_ratio": coverage,
        },
        "ordering_validation": {
            "raw_ordering_violations": ordering_violations,
            "normalized_event_count": len(normalized_events),
            "ordering_pass": ordering_violations == 0,
        },
        "integrity_validation": {
            "issue_count": len(integrity_issues),
            "issues": sorted(set(integrity_issues)),
            "integrity_pass": len(integrity_issues) == 0,
        },
        "summary": {
            "event_count": len(normalized_events),
            "source_count": len(sources),
            "governance_ok": governance_ok,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _token_hit_count(texts: list[str], token: str) -> int:
    key = str(token).strip().lower()
    if not key:
        return 0
    return sum(1 for text in texts if key in text.lower())


def _infer_construct_domain(construct: str, replacement: str) -> str:
    text = f"{construct} {replacement}".lower()
    if any(token in text for token in ("soundwire", "swr", "sdw")):
        return "SOUNDWIRE"
    if any(token in text for token in ("dapm", "widget", "route")):
        return "DAPM"
    if any(token in text for token in ("pcm", "dpcm", "fe", "be", "dai")):
        return "PCM"
    if any(token in text for token in ("dsp", "mailbox", "apr", "q6")):
        return "DSP"
    return "GENERIC"


def _build_runtime_equivalence_fingerprint(
    *,
    target_id: str,
    translation_artifacts: Mapping[str, Any],
    normalized_events: list[Mapping[str, Any]],
    evidence_quality_report: Mapping[str, Any],
    governance_ok: bool,
    evidence_references: list[str],
) -> dict[str, Any]:
    runtime_equivalence = _as_dict(translation_artifacts.get("runtime_equivalence_validation"))
    api_replacement_map = _as_dict(translation_artifacts.get("api_replacement_map"))
    candidates = [row for row in _as_list(runtime_equivalence.get("candidate_validations")) if isinstance(row, dict)]
    replacements = {
        str(_as_dict(row).get("downstream_construct", "")).strip().lower(): _as_dict(row)
        for row in _as_list(api_replacement_map.get("replacements"))
        if isinstance(row, dict)
    }

    messages = [str(_as_dict(event).get("message", "")) for event in normalized_events]
    domain_set = {str(_as_dict(event).get("domain", "")) for event in normalized_events}
    quality_score = _to_float(_as_dict(evidence_quality_report).get("quality_score", 0.0), 0.0)
    threshold = 0.72

    fingerprints: list[dict[str, Any]] = []
    for row in sorted(candidates, key=lambda item: str(_as_dict(item).get("downstream_construct", "")).lower()):
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip()
        if not construct:
            continue
        replacement_row = _as_dict(replacements.get(construct.lower()))
        replacement = str(replacement_row.get("upstream_replacement", "UNRESOLVED")).strip()
        validation_conf = _to_float(item.get("validation_confidence", 0.0), 0.0)
        runtime_equivalent = bool(item.get("runtime_equivalent", False))

        construct_hits = _token_hit_count(messages, construct)
        replacement_hits = _token_hit_count(messages, replacement) if replacement and replacement != "UNRESOLVED" else 0
        observed_match_score = round(min(1.0, (construct_hits + replacement_hits) / 4.0), 3)
        expected_domain = _infer_construct_domain(construct, replacement)
        domain_alignment = expected_domain == "GENERIC" or expected_domain in domain_set
        runtime_backed_confidence = round(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * validation_conf
                    + 0.35 * observed_match_score
                    + 0.20 * quality_score,
                ),
            ),
            3,
        )
        if not runtime_equivalent:
            runtime_backed_confidence = round(runtime_backed_confidence * 0.35, 3)
        if not domain_alignment:
            runtime_backed_confidence = round(runtime_backed_confidence * 0.8, 3)

        usable = bool(
            governance_ok
            and runtime_equivalent
            and domain_alignment
            and quality_score >= 0.68
            and runtime_backed_confidence >= threshold
        )

        fp_payload = {
            "target_id": str(target_id),
            "downstream_construct": construct,
            "upstream_replacement": replacement,
            "runtime_equivalent": runtime_equivalent,
            "validation_confidence": validation_conf,
            "observed_match_score": observed_match_score,
            "domain_alignment": domain_alignment,
            "runtime_backed_confidence": runtime_backed_confidence,
            "reusable_for_transformations": usable,
        }
        fp = dict(fp_payload)
        fp["equivalence_fingerprint"] = stable_fingerprint(fp_payload)
        fp["blocking_runtime_reasons"] = [
            str(reason)
            for reason in _as_list(item.get("blocking_runtime_reasons"))
            if str(reason).strip()
        ]
        fingerprints.append(fp)

    governed_reusable = [row for row in fingerprints if bool(_as_dict(row).get("reusable_for_transformations", False))]
    classification = "PASS"
    if not governance_ok:
        classification = "FAIL_CLOSED"
    elif quality_score < 0.68:
        classification = "FAIL_CLOSED"
    elif not governed_reusable:
        classification = "FAIL_CLOSED"

    report = {
        "schema_version": "1.0",
        "report_name": "runtime_equivalence_fingerprint",
        "target_id": str(target_id),
        "classification": classification,
        "transformations_require_runtime_backed_confidence_threshold": threshold,
        "entries": fingerprints,
        "summary": {
            "candidate_count": len(fingerprints),
            "governed_reusable_count": len(governed_reusable),
            "mean_runtime_backed_confidence": round(
                sum(_to_float(_as_dict(row).get("runtime_backed_confidence", 0.0), 0.0) for row in fingerprints)
                / max(1, len(fingerprints)),
                3,
            ),
            "quality_score": quality_score,
        },
        "governance_gate": {
            "requires_runtime_backed_evidence_confidence_above_threshold": True,
            "runtime_backed_confidence_threshold": threshold,
            "transformations_allowed": classification == "PASS",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_runtime_diff(
    *,
    target_id: str,
    translation_artifacts: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    hardware_truth_graph: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    translation_plan = _as_dict(translation_artifacts.get("upstream_translation_plan"))
    runtime_equivalence = _as_dict(translation_artifacts.get("runtime_equivalence_validation"))
    expected_stages = [
        str(_as_dict(stage).get("stage_id", "")).strip()
        for stage in _as_list(_as_dict(translation_plan.get("ast_aware_conversion_plan")).get("stages"))
        if str(_as_dict(stage).get("stage_id", "")).strip()
    ]

    observed_domains = sorted(
        set(
            str(key)
            for key in _as_dict(_as_dict(hardware_truth_graph).get("summary")).get("domain_counts", {}).keys()
            if str(key).strip()
        )
    )
    expected_domains = sorted(
        {
            "PCM",
            "DAPM",
            "SOUNDWIRE",
            "DSP",
            "IRQ",
            "CLOCK",
            "REGULATOR",
            "IPC",
        }
    )

    missing_domains = [domain for domain in expected_domains if domain not in observed_domains]
    unexpected_domains = [domain for domain in observed_domains if domain not in expected_domains]

    fingerprint_entries = [row for row in _as_list(runtime_equivalence_fingerprint.get("entries")) if isinstance(row, dict)]
    low_conf = [
        row
        for row in fingerprint_entries
        if _to_float(_as_dict(row).get("runtime_backed_confidence", 0.0), 0.0)
        < _to_float(runtime_equivalence_fingerprint.get("transformations_require_runtime_backed_confidence_threshold", 0.72), 0.72)
    ]

    non_equivalent = [
        row
        for row in _as_list(runtime_equivalence.get("candidate_validations"))
        if isinstance(row, dict) and not bool(_as_dict(row).get("runtime_equivalent", False))
    ]

    diff = {
        "schema_version": "1.0",
        "report_name": "downstream_upstream_runtime_diff",
        "target_id": str(target_id),
        "classification": "PASS" if (not missing_domains and not non_equivalent and not low_conf) else "FAIL_CLOSED",
        "expected_runtime_model": {
            "expected_stages": expected_stages,
            "expected_domains": expected_domains,
        },
        "observed_runtime_model": {
            "observed_domains": observed_domains,
            "observed_domain_counts": _as_dict(_as_dict(hardware_truth_graph).get("summary")).get("domain_counts", {}),
        },
        "divergence": {
            "missing_domains": missing_domains,
            "unexpected_domains": unexpected_domains,
            "non_equivalent_candidates": [
                str(_as_dict(row).get("downstream_construct", ""))
                for row in non_equivalent
                if str(_as_dict(row).get("downstream_construct", "")).strip()
            ],
            "low_confidence_candidates": [
                str(_as_dict(row).get("downstream_construct", ""))
                for row in low_conf
                if str(_as_dict(row).get("downstream_construct", "")).strip()
            ],
        },
        "summary": {
            "missing_domain_count": len(missing_domains),
            "non_equivalent_count": len(non_equivalent),
            "low_confidence_count": len(low_conf),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    diff["deterministic_fingerprint"] = stable_fingerprint(diff)
    return diff


def _build_runtime_divergence_report(
    *,
    target_id: str,
    runtime_diff: Mapping[str, Any],
    evidence_quality_report: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    previous_session_history: list[Mapping[str, Any]],
    governance_ok: bool,
    governance_reasons: list[str],
    evidence_references: list[str],
) -> dict[str, Any]:
    diff = _as_dict(runtime_diff)
    quality = _as_dict(evidence_quality_report)
    equiv = _as_dict(runtime_equivalence_fingerprint)
    history = [row for row in _as_list(previous_session_history) if isinstance(row, dict)]

    quality_score = _to_float(quality.get("quality_score", 0.0), 0.0)
    reusable_count = int(_as_dict(equiv.get("summary")).get("governed_reusable_count", 0))
    missing_domains = int(_as_dict(diff.get("summary")).get("missing_domain_count", 0))
    non_equivalent_count = int(_as_dict(diff.get("summary")).get("non_equivalent_count", 0))

    classification = "PASS"
    fail_closed_justification = ""
    if not governance_ok:
        classification = "FAIL_CLOSED"
        fail_closed_justification = ";".join(governance_reasons)
    elif str(quality.get("classification", "UNKNOWN")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = "evidence_quality_fail_closed"
    elif str(equiv.get("classification", "UNKNOWN")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_equivalence_confidence_below_threshold"
    elif str(diff.get("classification", "UNKNOWN")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_divergence_detected"

    cross_platform_rows = []
    current_fp = str(equiv.get("deterministic_fingerprint", ""))
    for row in history:
        item = _as_dict(row)
        other_target = str(item.get("target_id", "")).strip()
        if not other_target or other_target == str(target_id):
            continue
        other_score = _to_float(item.get("evidence_quality_score", 0.0), 0.0)
        other_reusable = int(item.get("governed_reusable_count", 0))
        cross_platform_rows.append(
            {
                "target_id": other_target,
                "classification": str(item.get("classification", "UNKNOWN")),
                "evidence_quality_delta": round(quality_score - other_score, 3),
                "reusable_equivalence_delta": int(reusable_count - other_reusable),
                "same_equivalence_fingerprint": str(item.get("runtime_equivalence_fingerprint", "")) == current_fp,
            }
        )

    report = {
        "schema_version": "1.0",
        "report_name": "runtime_divergence_report",
        "target_id": str(target_id),
        "classification": classification,
        "fail_closed_justification": fail_closed_justification,
        "divergence_signals": {
            "missing_domain_count": missing_domains,
            "non_equivalent_count": non_equivalent_count,
            "governed_reusable_count": reusable_count,
            "evidence_quality_score": quality_score,
        },
        "cross_platform_comparison": cross_platform_rows,
        "summary": {
            "history_comparison_count": len(cross_platform_rows),
            "governance_ok": governance_ok,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_target_session_replay(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    classification: str,
    artifact_fingerprints: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    previous_session_history: list[Mapping[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    lineage = [
        row for row in _as_list(previous_session_history) if isinstance(row, dict)
    ] + [
        {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "target_id": str(target_id),
            "classification": str(classification),
        }
    ]

    replay = {
        "schema_version": "1.0",
        "report_name": "target_session_replay",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(classification),
        "artifact_fingerprints": {str(k): str(v) for k, v in sorted(_as_dict(artifact_fingerprints).items())},
        "replay_signal": {
            "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": lineage[-5000:],
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    replay["deterministic_fingerprint"] = stable_fingerprint(replay)
    return replay


class RuntimeEvidenceAcquisitionEngine:
    """Runtime evidence acquisition and hardware truth validation engine."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        source_payloads: Mapping[str, Any],
        translation_artifacts: Mapping[str, Any],
        runtime_artifacts: Mapping[str, Any],
        ipcat_hardware_metadata: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_session_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> RuntimeEvidenceAcquisitionResult:
        plugin = self._plugins.load_plugin(target_id)
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": _as_dict(runtime_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": _as_dict(runtime_artifacts.get("dts_topology_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        subsystem_descriptor = _as_dict(
            plugin.subsystem_descriptor_provider(
                {
                    "static_context": _as_dict(runtime_artifacts.get("dts_topology_graph")),
                    "topology": _as_dict(runtime_artifacts.get("topology_runtime_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]
        history = [row for row in _as_list(previous_session_history or []) if isinstance(row, dict)]

        governance_ok, governance_reasons = _governance_clean(governance_state)
        ingested_sources = _ingest_live_sources(source_payloads)
        raw_events, normalized_events = _normalize_events(ingested_sources)

        ipc_topology_map = _build_ipc_topology_map(
            target_id=target_id,
            ipcat_descriptor=ipcat_hardware_metadata,
            topology_adapter=topology_adapter,
            normalized_events=normalized_events,
            evidence_references=evidence,
        )
        hardware_truth_graph = _build_runtime_topology(
            target_id=target_id,
            normalized_events=normalized_events,
            ipc_topology_map=ipc_topology_map,
        )
        target_runtime_capture = _build_target_runtime_capture(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            ingested_sources=ingested_sources,
            normalized_events=normalized_events,
            ipc_topology_map=ipc_topology_map,
            evidence_references=evidence,
        )

        evidence_quality = _build_evidence_quality_report(
            target_id=target_id,
            raw_events=raw_events,
            normalized_events=normalized_events,
            ingested_sources=ingested_sources,
            governance_ok=governance_ok,
            evidence_references=evidence,
        )
        runtime_equivalence_fingerprint = _build_runtime_equivalence_fingerprint(
            target_id=target_id,
            translation_artifacts=translation_artifacts,
            normalized_events=normalized_events,
            evidence_quality_report=evidence_quality,
            governance_ok=governance_ok,
            evidence_references=evidence,
        )
        runtime_diff = _build_runtime_diff(
            target_id=target_id,
            translation_artifacts=translation_artifacts,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            hardware_truth_graph=hardware_truth_graph,
            evidence_references=evidence,
        )
        runtime_divergence = _build_runtime_divergence_report(
            target_id=target_id,
            runtime_diff=runtime_diff,
            evidence_quality_report=evidence_quality,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            previous_session_history=history,
            governance_ok=governance_ok,
            governance_reasons=governance_reasons,
            evidence_references=evidence,
        )

        artifacts = {
            "runtime_equivalence_fingerprint": runtime_equivalence_fingerprint,
            "hardware_truth_graph": hardware_truth_graph,
            "target_runtime_capture": target_runtime_capture,
            "downstream_upstream_runtime_diff": runtime_diff,
            "ipc_topology_map": ipc_topology_map,
            "evidence_quality_report": evidence_quality,
            "runtime_divergence_report": runtime_divergence,
        }

        target_session_replay = _build_target_session_replay(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            classification=str(runtime_divergence.get("classification", "UNKNOWN")),
            artifact_fingerprints={
                name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                for name, payload in sorted(artifacts.items())
            },
            replay_traces=replay_traces,
            previous_session_history=history,
            evidence_references=evidence,
        )
        artifacts["target_session_replay"] = target_session_replay

        bundle = {
            "schema_version": "1.0",
            "phase": "RUNTIME_EVIDENCE_ACQUISITION_AND_HARDWARE_TRUTH_VALIDATION",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": str(runtime_divergence.get("classification", "UNKNOWN")),
            "fail_closed_justification": str(runtime_divergence.get("fail_closed_justification", "")),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "topology_evidence": topology_adapter,
                "subsystem_descriptor": subsystem_descriptor,
            },
            "artifacts": artifacts,
            "evidence_references": evidence,
        }
        bundle["runtime_evidence_acquisition_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": str(bundle.get("classification", "UNKNOWN")),
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "adapter_fingerprints": {
                    "topology_evidence": str(topology_adapter.get("fingerprint", "")),
                    "subsystem_descriptor": str(subsystem_descriptor.get("fingerprint", "")),
                },
            }
        )

        return RuntimeEvidenceAcquisitionResult(acquisition_bundle=bundle)


class RuntimeEvidenceAcquisitionRegistry:
    """Replay-safe persistence for runtime evidence acquisition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "runtime_equivalence_fingerprint": self._output_dir / "runtime_equivalence_fingerprint.json",
            "hardware_truth_graph": self._output_dir / "hardware_truth_graph.json",
            "target_runtime_capture": self._output_dir / "target_runtime_capture.json",
            "downstream_upstream_runtime_diff": self._output_dir / "downstream_upstream_runtime_diff.json",
            "ipc_topology_map": self._output_dir / "ipc_topology_map.json",
            "evidence_quality_report": self._output_dir / "evidence_quality_report.json",
            "runtime_divergence_report": self._output_dir / "runtime_divergence_report.json",
            "target_session_replay": self._output_dir / "target_session_replay.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_acquisition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        quality = _as_dict(artifacts.get("evidence_quality_report"))
        eq = _as_dict(artifacts.get("runtime_equivalence_fingerprint"))
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "runtime_evidence_acquisition_fingerprint": str(payload.get("runtime_evidence_acquisition_fingerprint", "")),
            "runtime_equivalence_fingerprint": str(eq.get("deterministic_fingerprint", "")),
            "evidence_quality_score": _to_float(quality.get("quality_score", 0.0), 0.0),
            "governed_reusable_count": int(_as_dict(eq.get("summary")).get("governed_reusable_count", 0)),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-6000:]

        registry["runtime_evidence_acquisition"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        cognition_lineage = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        cognition_lineage.append(
            {
                "lineage_id": lineage_id,
                "type": "runtime_evidence_acquisition",
                "recorded_at": _utc_now_iso(),
                "runtime_evidence_acquisition_fingerprint": str(
                    payload.get("runtime_evidence_acquisition_fingerprint", "")
                ),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = cognition_lineage[-22000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "runtime_evidence_acquisition_fingerprint": entry["runtime_evidence_acquisition_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_acquisition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "runtime_evidence_acquisition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "runtime_evidence_acquisition_fingerprint": str(
                _as_dict(selected).get("runtime_evidence_acquisition_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "runtime_evidence_acquisition_fingerprint": str(
                        _as_dict(selected).get("runtime_evidence_acquisition_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "target_session_replay.json", replay_payload)
        return replay_payload
