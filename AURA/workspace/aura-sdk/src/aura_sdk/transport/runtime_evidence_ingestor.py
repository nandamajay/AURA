"""Real Runtime Evidence Ingestion Layer orchestration.

This layer ingests read-only runtime evidence streams, normalizes cross-source
records, correlates with persisted cognition artifacts, and emits deterministic
session artifacts for replay-safe engineering observability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from aura_sdk.transport.debugfs_runtime_ingestor import ingest_debugfs_runtime
from aura_sdk.transport.dmesg_ingestor import ingest_dmesg
from aura_sdk.transport.dsp_mailbox_ingestor import ingest_dsp_mailbox
from aura_sdk.transport.engineering_session_replay import (
    EngineeringSessionReplayResult,
    build_engineering_session_replay,
)
from aura_sdk.transport.ftrace_ingestor import ingest_ftrace
from aura_sdk.transport.irq_runtime_ingestor import ingest_irq_runtime
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.procfs_runtime_ingestor import ingest_procfs_runtime
from aura_sdk.transport.runtime_capture_fingerprint import (
    RuntimeCaptureFingerprintResult,
    build_runtime_capture_fingerprint,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.soundwire_runtime_ingestor import ingest_soundwire_runtime
from aura_sdk.transport.tinymix_state_ingestor import ingest_tinymix_state
from aura_sdk.transport.tracecmd_ingestor import ingest_tracecmd


_REQUIRED_SOURCE_KEYS = [
    "dmesg",
    "ftrace",
    "trace_cmd",
    "perf",
    "tinymix_state",
    "procfs_runtime",
    "debugfs_runtime",
    "soundwire_runtime",
    "dsp_mailbox",
    "irq_runtime",
]

_AUTONOMOUS_POLICY_FLAGS = [
    "autonomous_patching_allowed",
    "autonomous_topology_rewrite_allowed",
    "autonomous_runtime_mutation_allowed",
    "autonomous_upstream_generation_allowed",
]

_FE_RE = re.compile(r"\b(?:fe|frontend|multimedia)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)
_BE_RE = re.compile(r"\b(?:be|backend|rx|tx)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)
_SWR_RE = re.compile(r"\b(swr[a-z0-9_:-]*|soundwire[a-z0-9_:-]*)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RuntimeEvidenceIngestionResult:
    runtime_evidence_bundle: dict[str, Any]


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


def _to_float(value: Any, default: float) -> float:
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


def _subsystem_identity(source: str, event_type: str, message: str) -> tuple[str, str]:
    text = f"{source} {event_type} {message}".lower()
    if any(token in text for token in ("mailbox", "adsp", "dsp", "apr")):
        return "DSP", "dsp"
    if "soundwire" in text or "swr" in text:
        return "SOUNDWIRE", "soundwire"
    if "irq" in text or "interrupt" in text:
        return "IRQ", "irq"
    if any(token in text for token in ("dapm", "widget", "power_up", "power_down")):
        return "DAPM", "dapm"
    if any(token in text for token in ("pcm", "dpcm", "aplay", "prepare", "start", "stop", "close", "drain", "fe", "be")):
        return "ALSA_PCM", "alsa_pcm"
    if any(token in text for token in ("mixer", "tinymix", "amixer")):
        return "MIXER", "mixer"
    if any(token in text for token in ("procfs", "asound", "sysfs", "debugfs", "topology")):
        return "KERNEL_STATE", "kernel_state"
    if any(token in text for token in ("dmesg", "kernel_log", "log")):
        return "KERNEL_LOG", "kernel_log"
    return "GENERIC", "generic"


def _extract_fe_ref(message: str) -> str:
    match = _FE_RE.search(message)
    if not match:
        return ""
    return f"FE{match.group(1)}"


def _extract_be_ref(message: str) -> str:
    match = _BE_RE.search(message)
    if not match:
        return ""
    return f"BE{match.group(1)}"


def _extract_soundwire_entity(event: Mapping[str, Any], message: str) -> str:
    explicit = str(event.get("entity", "")).strip()
    if explicit:
        return explicit.lower()
    match = _SWR_RE.search(message)
    if not match:
        return ""
    return match.group(1).lower()


def _extract_dpcm_state(message: str) -> str:
    lowered = message.lower()
    if "open" in lowered:
        return "OPEN"
    if "prepare" in lowered:
        return "PREPARE"
    if "start" in lowered:
        return "START"
    if "pause" in lowered:
        return "PAUSE"
    if "resume" in lowered:
        return "RESUME"
    if "drain" in lowered:
        return "DRAIN"
    if "stop" in lowered:
        return "STOP"
    if "close" in lowered:
        return "CLOSE"
    return "UNKNOWN"


def _normalize_runtime_events(source_artifacts: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for source_key in sorted(source_artifacts.keys()):
        artifact = _as_dict(source_artifacts.get(source_key))
        events = [row for row in _as_list(artifact.get("events")) if isinstance(row, dict)]

        for event in events:
            source = str(event.get("source", source_key)).strip() or source_key
            event_type = str(event.get("event_type", "runtime_event")).strip() or "runtime_event"
            message = str(event.get("message", event.get("detail", ""))).strip()
            ts = _to_float(event.get("timestamp_ms", 0.0), 0.0)
            subsystem, subsystem_id = _subsystem_identity(source, event_type, message)

            rows.append(
                {
                    "event_id": str(event.get("event_id", "")).strip() or f"{source_key}:{len(rows) + 1}",
                    "source_key": source_key,
                    "source": source,
                    "timestamp_ms": round(ts, 3),
                    "event_type": event_type,
                    "message": message,
                    "subsystem": subsystem,
                    "subsystem_id": subsystem_id,
                    "fe_reference": _extract_fe_ref(message),
                    "be_reference": _extract_be_ref(message),
                    "dpcm_lifecycle_state": _extract_dpcm_state(message),
                    "dsp_lineage_id": str(event.get("dsp_lineage_id", "")).strip(),
                    "soundwire_entity": _extract_soundwire_entity(event, message),
                    "raw": event,
                }
            )

    rows.sort(key=lambda row: (float(row.get("timestamp_ms", 0.0)), str(row.get("event_id", ""))))

    dsp_counter = 0
    for row in rows:
        dsp_lineage = str(row.get("dsp_lineage_id", "")).strip()
        if dsp_lineage:
            continue
        if str(row.get("subsystem", "")) == "DSP":
            dsp_counter += 1
            row["dsp_lineage_id"] = f"dsp_lineage:{dsp_counter}"

    return rows


def _domain_artifacts(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    data = _as_dict(payload)
    domains = {
        "topology_cognition": _as_dict(data.get("topology_cognition", data.get("topology_runtime_graph"))),
        "runtime_truth_graph": _as_dict(data.get("runtime_truth_graph")),
        "migration_lineage": _as_dict(data.get("migration_lineage", data.get("migration_runtime_alignment"))),
        "patch_lineage": _as_dict(data.get("patch_lineage", data.get("patch_runtime_lineage"))),
        "structural_cognition": _as_dict(data.get("structural_cognition", data.get("structural_graph"))),
        "semantic_ontology": _as_dict(data.get("semantic_ontology", data.get("semantic_ontology_graph"))),
    }
    return domains


def _event_domain_links(event: Mapping[str, Any], domains: Mapping[str, Any]) -> list[str]:
    subsystem = str(event.get("subsystem", "")).upper()
    linked: list[str] = []

    for domain in sorted(domains.keys()):
        if not _as_dict(domains.get(domain)):
            continue

        if subsystem in {"ALSA_PCM", "DAPM", "MIXER"}:
            if domain in {"topology_cognition", "runtime_truth_graph", "semantic_ontology", "structural_cognition"}:
                linked.append(domain)
        elif subsystem == "SOUNDWIRE":
            if domain in {"topology_cognition", "runtime_truth_graph", "semantic_ontology", "structural_cognition", "migration_lineage"}:
                linked.append(domain)
        elif subsystem == "DSP":
            if domain in {"runtime_truth_graph", "patch_lineage", "migration_lineage", "semantic_ontology"}:
                linked.append(domain)
        elif subsystem == "IRQ":
            if domain in {"runtime_truth_graph", "patch_lineage", "migration_lineage"}:
                linked.append(domain)
        else:
            if domain in {"runtime_truth_graph", "semantic_ontology"}:
                linked.append(domain)

    return sorted(set(linked))


def _build_subsystem_state(normalized_events: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}

    for event in normalized_events:
        key = str(event.get("subsystem_id", "generic"))
        state = grouped.setdefault(
            key,
            {
                "subsystem": str(event.get("subsystem", "GENERIC")),
                "subsystem_id": key,
                "event_count": 0,
                "first_timestamp_ms": None,
                "last_timestamp_ms": None,
                "sources": set(),
                "fe_references": set(),
                "be_references": set(),
                "dpcm_states": set(),
                "dsp_lineages": set(),
                "soundwire_entities": set(),
            },
        )

        ts = _to_float(event.get("timestamp_ms", 0.0), 0.0)
        state["event_count"] = int(state["event_count"]) + 1
        state["sources"].add(str(event.get("source_key", "")))

        if state["first_timestamp_ms"] is None or ts < _to_float(state["first_timestamp_ms"], ts):
            state["first_timestamp_ms"] = round(ts, 3)
        if state["last_timestamp_ms"] is None or ts > _to_float(state["last_timestamp_ms"], ts):
            state["last_timestamp_ms"] = round(ts, 3)

        fe_ref = str(event.get("fe_reference", "")).strip()
        if fe_ref:
            state["fe_references"].add(fe_ref)

        be_ref = str(event.get("be_reference", "")).strip()
        if be_ref:
            state["be_references"].add(be_ref)

        dpcm = str(event.get("dpcm_lifecycle_state", "UNKNOWN")).strip()
        if dpcm:
            state["dpcm_states"].add(dpcm)

        dsp_lineage = str(event.get("dsp_lineage_id", "")).strip()
        if dsp_lineage:
            state["dsp_lineages"].add(dsp_lineage)

        swr_entity = str(event.get("soundwire_entity", "")).strip()
        if swr_entity:
            state["soundwire_entities"].add(swr_entity)

    subsystems = []
    for subsystem_id in sorted(grouped.keys()):
        state = grouped[subsystem_id]
        subsystems.append(
            {
                "subsystem": str(state["subsystem"]),
                "subsystem_id": subsystem_id,
                "event_count": int(state["event_count"]),
                "first_timestamp_ms": state["first_timestamp_ms"],
                "last_timestamp_ms": state["last_timestamp_ms"],
                "sources": sorted(state["sources"]),
                "fe_references": sorted(state["fe_references"]),
                "be_references": sorted(state["be_references"]),
                "dpcm_states": sorted(state["dpcm_states"]),
                "dsp_lineage_count": len(state["dsp_lineages"]),
                "soundwire_entity_count": len(state["soundwire_entities"]),
            }
        )

    payload = {
        "schema_version": "1.0",
        "report_name": "subsystem_runtime_state",
        "subsystems": subsystems,
        "summary": {
            "subsystem_count": len(subsystems),
            "total_events": sum(int(item.get("event_count", 0)) for item in subsystems),
        },
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_pcm_runtime_state(normalized_events: list[dict[str, Any]]) -> dict[str, Any]:
    pcm_events = [
        event
        for event in normalized_events
        if str(event.get("subsystem", "")) in {"ALSA_PCM", "DAPM"}
        or str(event.get("dpcm_lifecycle_state", "UNKNOWN")) != "UNKNOWN"
    ]

    states = [
        {
            "event_id": str(event.get("event_id", "")),
            "timestamp_ms": round(_to_float(event.get("timestamp_ms", 0.0), 0.0), 3),
            "source": str(event.get("source", "")),
            "dpcm_lifecycle_state": str(event.get("dpcm_lifecycle_state", "UNKNOWN")),
            "fe_reference": str(event.get("fe_reference", "")),
            "be_reference": str(event.get("be_reference", "")),
            "message": str(event.get("message", "")),
        }
        for event in pcm_events
    ]

    active_duration = 0.0
    if states:
        first_ts = _to_float(states[0].get("timestamp_ms", 0.0), 0.0)
        last_ts = _to_float(states[-1].get("timestamp_ms", first_ts), first_ts)
        active_duration = round(max(0.0, last_ts - first_ts), 3)

    payload = {
        "schema_version": "1.0",
        "report_name": "pcm_runtime_state",
        "states": states,
        "summary": {
            "event_count": len(states),
            "active_duration_ms": active_duration,
            "observed_lifecycle_states": sorted(
                {
                    str(item.get("dpcm_lifecycle_state", "UNKNOWN"))
                    for item in states
                    if str(item.get("dpcm_lifecycle_state", "UNKNOWN")).strip()
                }
            ),
            "unique_fe_references": sorted(
                {
                    str(item.get("fe_reference", ""))
                    for item in states
                    if str(item.get("fe_reference", "")).strip()
                }
            ),
            "unique_be_references": sorted(
                {
                    str(item.get("be_reference", ""))
                    for item in states
                    if str(item.get("be_reference", "")).strip()
                }
            ),
        },
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_domain_correlation(
    normalized_events: list[dict[str, Any]],
    domain_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    present_domains = {
        name: _as_dict(payload)
        for name, payload in sorted(_as_dict(domain_artifacts).items())
        if _as_dict(payload)
    }

    linked_event_count = 0
    domain_hits = {name: 0 for name in present_domains}

    correlated_events: list[dict[str, Any]] = []
    for event in normalized_events:
        links = _event_domain_links(event, present_domains)
        if links:
            linked_event_count += 1
            for domain in links:
                domain_hits[domain] = int(domain_hits.get(domain, 0)) + 1

        correlated_events.append(
            {
                "event_id": str(event.get("event_id", "")),
                "source_key": str(event.get("source_key", "")),
                "subsystem_id": str(event.get("subsystem_id", "generic")),
                "linked_domains": links,
            }
        )

    summary = {
        "present_domains": sorted(present_domains.keys()),
        "domain_count": len(present_domains),
        "linked_event_count": linked_event_count,
        "unlinked_event_count": max(0, len(normalized_events) - linked_event_count),
        "domain_hit_counts": domain_hits,
        "domain_fingerprints": {
            name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for name, payload in sorted(present_domains.items())
        },
    }

    return {
        "correlated_events": correlated_events,
        "summary": summary,
    }


def _build_runtime_session_graph(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    source_status: Mapping[str, Any],
    subsystem_runtime_state: Mapping[str, Any],
    domain_correlation: Mapping[str, Any],
    classification: str,
) -> dict[str, Any]:
    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": f"session:{session_id}", "kind": "runtime_session"},
        {"id": f"lineage:{lineage_id}", "kind": "lineage"},
    ]
    edges = [
        {"from": f"target:{target_id}", "to": f"session:{session_id}", "relation": "captures"},
        {"from": f"session:{session_id}", "to": f"lineage:{lineage_id}", "relation": "tracked_by"},
    ]

    for source in sorted(source_status.keys()):
        source_id = f"source:{source}"
        nodes.append({"id": source_id, "kind": "evidence_source"})
        edges.append({"from": f"session:{session_id}", "to": source_id, "relation": "ingested"})

    for subsystem in _as_list(_as_dict(subsystem_runtime_state).get("subsystems")):
        item = _as_dict(subsystem)
        subsystem_id = str(item.get("subsystem_id", "generic"))
        node_id = f"subsystem:{subsystem_id}"
        nodes.append({"id": node_id, "kind": "runtime_subsystem"})
        edges.append({"from": f"session:{session_id}", "to": node_id, "relation": "observed"})

    correlation_summary = _as_dict(domain_correlation.get("summary"))
    for domain in _as_list(correlation_summary.get("present_domains")):
        domain_key = str(domain)
        node_id = f"domain:{domain_key}"
        nodes.append({"id": node_id, "kind": "cognition_domain"})
        edges.append({"from": f"session:{session_id}", "to": node_id, "relation": "correlated"})

    payload = {
        "schema_version": "1.0",
        "graph_name": "runtime_session_graph",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(classification),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "source_count": len(source_status),
            "subsystem_count": len(_as_list(_as_dict(subsystem_runtime_state).get("subsystems"))),
            "domain_count": len(_as_list(correlation_summary.get("present_domains"))),
        },
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_capture_lineage(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    source_status: Mapping[str, Any],
    source_fingerprints: Mapping[str, Any],
    evidence_references: list[str],
    classification: str,
) -> dict[str, Any]:
    ordering = sorted(source_status.keys())
    previous_hash = ""
    captures: list[dict[str, Any]] = []

    for index, source in enumerate(ordering, start=1):
        status = _as_dict(source_status.get(source))
        entry = {
            "capture_id": f"capture:{session_id}:{source}",
            "source": source,
            "capture_order": index,
            "capture_offset_ms": round(1000.0 + index * 5.0, 3),
            "classification": str(status.get("classification", "MISSING")),
            "event_count": int(status.get("event_count", 0) or 0),
            "source_fingerprint": str(_as_dict(source_fingerprints).get(source, "")),
            "previous_hash": previous_hash,
        }
        entry_hash = stable_fingerprint(entry)
        entry["entry_hash"] = entry_hash
        previous_hash = entry_hash
        captures.append(entry)

    payload = {
        "schema_version": "1.0",
        "report_name": "evidence_capture_lineage",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(classification),
        "capture_sequence": captures,
        "summary": {
            "capture_count": len(captures),
            "final_chain_hash": previous_hash,
        },
        "immutable_history": True,
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
        "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _governance_is_clean(governance_state: Mapping[str, Any]) -> bool:
    governance = _as_dict(governance_state)
    if not bool(governance.get("fail_closed_posture", True)):
        return False
    for flag in _AUTONOMOUS_POLICY_FLAGS:
        if _is_true(governance.get(flag, False)):
            return False
    return True


def _timestamp_order_score(normalized_events: list[dict[str, Any]]) -> float:
    if len(normalized_events) <= 1:
        return 1.0 if normalized_events else 0.0

    ordered = 0
    total = 0
    prev = None
    for event in normalized_events:
        ts = _to_float(event.get("timestamp_ms", 0.0), 0.0)
        if prev is not None:
            total += 1
            if ts >= prev:
                ordered += 1
        prev = ts

    if total == 0:
        return 1.0
    return round(ordered / total, 3)


class RuntimeEvidenceIngestor:
    """Deterministic runtime evidence ingestion orchestrator."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        session_id: str,
        source_payloads: Mapping[str, Any],
        domain_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_session_history: list[Mapping[str, Any]] | None,
    ) -> RuntimeEvidenceIngestionResult:
        plugin = self._plugins.load_plugin(target_id)

        artifacts = _domain_artifacts(domain_artifacts)

        runtime_adapter = _as_dict(
            plugin.runtime_evidence_adapter(
                {
                    "runtime_evidence": _as_dict(artifacts.get("runtime_truth_graph")),
                    "pcm_activity": _as_dict(artifacts.get("runtime_truth_graph")),
                    "mixer_state": _as_dict(source_payloads.get("tinymix_state")),
                    "replay_traces": dict(replay_traces),
                    "governance_decisions": dict(governance_state),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": _as_dict(artifacts.get("topology_cognition")),
                    "dts_cognition": _as_dict(artifacts.get("structural_cognition")),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        semantic_adapter = _as_dict(
            plugin.semantic_evidence_adapter(
                {
                    "semantic_cognition": _as_dict(artifacts.get("semantic_ontology")),
                    "regression_history": [row for row in _as_list(previous_session_history or []) if isinstance(row, dict)],
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        payloads = _as_dict(source_payloads)

        dmesg_result = ingest_dmesg(_as_dict(payloads.get("dmesg")))
        ftrace_result = ingest_ftrace(_as_dict(payloads.get("ftrace")))
        tracecmd_result = ingest_tracecmd(_as_dict(payloads.get("trace_cmd", payloads.get("tracecmd"))))
        perf_result = ingest_tracecmd(_as_dict(payloads.get("perf")))
        tinymix_result = ingest_tinymix_state(_as_dict(payloads.get("tinymix_state")))
        procfs_result = ingest_procfs_runtime(_as_dict(payloads.get("procfs_runtime")))
        debugfs_result = ingest_debugfs_runtime(_as_dict(payloads.get("debugfs_runtime")))
        soundwire_result = ingest_soundwire_runtime(_as_dict(payloads.get("soundwire_runtime")))
        dsp_result = ingest_dsp_mailbox(_as_dict(payloads.get("dsp_mailbox")))
        irq_result = ingest_irq_runtime(_as_dict(payloads.get("irq_runtime")))

        source_artifacts = {
            "dmesg": dmesg_result.dmesg_ingestion,
            "ftrace": ftrace_result.ftrace_ingestion,
            "trace_cmd": tracecmd_result.tracecmd_ingestion,
            "perf": {
                **perf_result.tracecmd_ingestion,
                "source": "perf",
                "events": [
                    {
                        **_as_dict(event),
                        "source": "perf",
                        "event_id": str(_as_dict(event).get("event_id", "")).replace("tracecmd:", "perf:"),
                    }
                    for event in _as_list(perf_result.tracecmd_ingestion.get("events"))
                ],
            },
            "tinymix_state": tinymix_result.tinymix_state_ingestion,
            "procfs_runtime": procfs_result.procfs_runtime_ingestion,
            "debugfs_runtime": debugfs_result.debugfs_runtime_ingestion,
            "soundwire_runtime": soundwire_result.soundwire_runtime_ingestion,
            "dsp_mailbox": dsp_result.dsp_mailbox_ingestion,
            "irq_runtime": irq_result.irq_runtime_ingestion,
        }

        source_fingerprints = {
            key: str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for key, payload in sorted(source_artifacts.items())
        }

        source_status = {
            key: {
                "classification": str(_as_dict(payload).get("classification", "MISSING")),
                "event_count": len(_as_list(_as_dict(payload).get("events"))),
            }
            for key, payload in sorted(source_artifacts.items())
        }

        missing_required_sources = [
            source
            for source in _REQUIRED_SOURCE_KEYS
            if str(_as_dict(source_status.get(source)).get("classification", "MISSING")) != "PRESENT"
        ]

        normalized_events = _normalize_runtime_events(source_artifacts)
        domain_correlation = _build_domain_correlation(normalized_events, artifacts)

        for event in normalized_events:
            event["correlated_domains"] = _as_list(
                _as_dict(
                    next(
                        (
                            row
                            for row in _as_list(domain_correlation.get("correlated_events"))
                            if str(_as_dict(row).get("event_id", "")) == str(event.get("event_id", ""))
                        ),
                        {},
                    )
                ).get("linked_domains", [])
            )

        subsystem_state = _build_subsystem_state(normalized_events)
        pcm_runtime_state = _build_pcm_runtime_state(normalized_events)

        dsp_runtime_trace = {
            "schema_version": "1.0",
            "report_name": "dsp_runtime_trace",
            "events": [
                event
                for event in normalized_events
                if str(event.get("subsystem", "")) == "DSP"
                or str(event.get("dsp_lineage_id", "")).strip()
            ],
            "summary": {
                "event_count": len(
                    [
                        event
                        for event in normalized_events
                        if str(event.get("subsystem", "")) == "DSP"
                        or str(event.get("dsp_lineage_id", "")).strip()
                    ]
                ),
                "lineage_count": len(
                    {
                        str(event.get("dsp_lineage_id", ""))
                        for event in normalized_events
                        if str(event.get("dsp_lineage_id", "")).strip()
                    }
                ),
            },
            "runtime_truth_precedence": True,
            "read_only_ingestion": True,
        }
        dsp_runtime_trace["deterministic_fingerprint"] = stable_fingerprint(dsp_runtime_trace)

        soundwire_runtime_trace = {
            "schema_version": "1.0",
            "report_name": "soundwire_runtime_trace",
            "events": [
                event
                for event in normalized_events
                if str(event.get("subsystem", "")) == "SOUNDWIRE"
                or str(event.get("soundwire_entity", "")).strip()
            ],
            "summary": {
                "event_count": len(
                    [
                        event
                        for event in normalized_events
                        if str(event.get("subsystem", "")) == "SOUNDWIRE"
                        or str(event.get("soundwire_entity", "")).strip()
                    ]
                ),
                "entity_count": len(
                    {
                        str(event.get("soundwire_entity", ""))
                        for event in normalized_events
                        if str(event.get("soundwire_entity", "")).strip()
                    }
                ),
            },
            "runtime_truth_precedence": True,
            "read_only_ingestion": True,
        }
        soundwire_runtime_trace["deterministic_fingerprint"] = stable_fingerprint(soundwire_runtime_trace)

        evidence_refs = [str(item) for item in (evidence_references or []) if str(item).strip()]

        governance_ok = _governance_is_clean(governance_state)
        timestamp_score = _timestamp_order_score(normalized_events)
        completeness_score = round(
            (len(_REQUIRED_SOURCE_KEYS) - len(missing_required_sources)) / max(1, len(_REQUIRED_SOURCE_KEYS)),
            3,
        )
        correlation_summary = _as_dict(domain_correlation.get("summary"))
        linked_event_count = int(correlation_summary.get("linked_event_count", 0) or 0)
        correlation_score = round(linked_event_count / max(1, len(normalized_events)), 3)

        evidence_confidence = round(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * completeness_score
                    + 0.25 * correlation_score
                    + 0.20 * timestamp_score
                    + 0.10 * (1.0 if governance_ok else 0.0),
                ),
            ),
            3,
        )

        classification = "PASS"
        if not governance_ok:
            classification = "FAIL_CLOSED"
        elif missing_required_sources or not normalized_events:
            classification = "FAIL_CLOSED"
        elif not _as_list(correlation_summary.get("present_domains")):
            classification = "FAIL_CLOSED"
        elif evidence_confidence < 0.70:
            classification = "ADVISORY_ONLY"

        normalized_runtime_evidence = {
            "schema_version": "1.0",
            "report_name": "normalized_runtime_evidence",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "normalized_events": normalized_events,
            "source_status": source_status,
            "summary": {
                "normalized_event_count": len(normalized_events),
                "missing_required_sources": missing_required_sources,
                "required_source_count": len(_REQUIRED_SOURCE_KEYS),
                "evidence_completeness": completeness_score,
                "timestamp_order_score": timestamp_score,
                "correlation_score": correlation_score,
                "evidence_confidence": evidence_confidence,
            },
            "domain_correlation": domain_correlation,
            "runtime_truth_precedence": True,
            "read_only_ingestion": True,
            "immutable_evidence_history": True,
            "evidence_references": evidence_refs,
        }
        normalized_runtime_evidence["deterministic_fingerprint"] = stable_fingerprint(normalized_runtime_evidence)

        runtime_session_graph = _build_runtime_session_graph(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            source_status=source_status,
            subsystem_runtime_state=subsystem_state,
            domain_correlation=domain_correlation,
            classification=classification,
        )

        evidence_capture_lineage = _build_capture_lineage(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            source_status=source_status,
            source_fingerprints=source_fingerprints,
            evidence_references=evidence_refs,
            classification=classification,
        )

        capture_result: RuntimeCaptureFingerprintResult = build_runtime_capture_fingerprint(
            target_id=target_id,
            session_id=session_id,
            normalized_runtime_evidence=normalized_runtime_evidence,
            source_fingerprints=source_fingerprints,
            evidence_references=evidence_refs,
        )

        artifacts: dict[str, Any] = {
            "normalized_runtime_evidence": normalized_runtime_evidence,
            "runtime_session_graph": runtime_session_graph,
            "evidence_capture_lineage": evidence_capture_lineage,
            "subsystem_runtime_state": subsystem_state,
            "dsp_runtime_trace": dsp_runtime_trace,
            "soundwire_runtime_trace": soundwire_runtime_trace,
            "pcm_runtime_state": pcm_runtime_state,
            "runtime_capture_fingerprint": capture_result.runtime_capture_fingerprint,
        }

        artifact_fingerprints = {
            key: str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for key, payload in sorted(artifacts.items())
        }

        replay_result: EngineeringSessionReplayResult = build_engineering_session_replay(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            runtime_capture_fingerprint=capture_result.runtime_capture_fingerprint,
            artifact_fingerprints=artifact_fingerprints,
            replay_traces=replay_traces,
            previous_history=[row for row in _as_list(previous_session_history or []) if isinstance(row, dict)],
            evidence_references=evidence_refs,
        )
        artifacts["deterministic_runtime_session_replay"] = replay_result.deterministic_runtime_session_replay

        runtime_evidence_ingestion_fingerprint = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "source_fingerprints": source_fingerprints,
                "artifact_fingerprints": {
                    key: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for key, payload in sorted(artifacts.items())
                },
                "adapter_fingerprints": {
                    "runtime": str(runtime_adapter.get("fingerprint", "")),
                    "topology": str(topology_adapter.get("fingerprint", "")),
                    "semantic": str(semantic_adapter.get("fingerprint", "")),
                },
            }
        )

        bundle = {
            "schema_version": "1.0",
            "phase": "REAL_RUNTIME_EVIDENCE_INGESTION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "source_status": source_status,
            "source_fingerprints": source_fingerprints,
            "plugin_adapters": {
                "runtime": runtime_adapter,
                "topology": topology_adapter,
                "semantic": semantic_adapter,
            },
            "replay_traces": dict(replay_traces),
            "evidence_references": evidence_refs,
            "artifacts": artifacts,
            "runtime_evidence_ingestion_fingerprint": runtime_evidence_ingestion_fingerprint,
            "confidence": {
                "evidence_confidence": evidence_confidence,
                "completeness_score": completeness_score,
                "correlation_score": correlation_score,
                "timestamp_order_score": timestamp_score,
                "governance_ok": governance_ok,
            },
        }

        return RuntimeEvidenceIngestionResult(runtime_evidence_bundle=bundle)
