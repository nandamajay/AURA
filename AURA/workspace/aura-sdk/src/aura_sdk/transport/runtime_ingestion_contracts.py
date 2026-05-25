"""Canonical contracts for runtime ingestion foundations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aura_sdk.transport.deterministic_serialization import deterministic_uuid, stable_sha256


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeLineageContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lineage_id: str
    session_id: str
    target_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    parent_lineage_id: str = ""


class RuntimeParserInputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_name: str
    parser_version: str
    source_type: Literal[
        "dmesg",
        "ftrace",
        "trace_cmd",
        "tinymix",
        "procfs",
        "debugfs",
        "soundwire",
        "dsp_mailbox",
        "irq",
        "clock",
        "regulator",
    ]
    source_uri: str
    lineage: RuntimeLineageContract


class RuntimeParserEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    timestamp_ms: float
    domain: str
    message: str
    source: str


class RuntimeParserOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_name: str
    parser_version: str
    source_type: str
    lineage: RuntimeLineageContract
    events: list[RuntimeParserEvent] = Field(default_factory=list)
    parse_classification: Literal["PASS", "FAIL_CLOSED"]
    fail_closed_reasons: list[str] = Field(default_factory=list)


class RuntimeGraphNode(BaseModel):
    model_config = ConfigDict(extra="allow")
    node_id: str
    node_type: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class RuntimeGraphEdge(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_node_id: str
    target_node_id: str
    relation: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class RuntimeGraphSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph_name: str
    lineage: RuntimeLineageContract
    nodes: list[RuntimeGraphNode] = Field(default_factory=list)
    edges: list[RuntimeGraphEdge] = Field(default_factory=list)
    classification: Literal["PASS", "FAIL_CLOSED"]
    fail_closed_reasons: list[str] = Field(default_factory=list)


class RuntimeEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    evidence_id: str
    evidence_type: str
    source_uri: str
    deterministic_fingerprint: str
    lineage_id: str


class RuntimeEvidenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_name: str = "runtime_evidence_schema"
    schema_version: str = "1.0"
    lineage: RuntimeLineageContract
    evidence: list[RuntimeEvidenceRecord] = Field(default_factory=list)
    classification: Literal["PASS", "FAIL_CLOSED"] = "PASS"
    fail_closed_reasons: list[str] = Field(default_factory=list)


class RuntimeReplaySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_name: str = "runtime_replay_schema"
    schema_version: str = "1.0"
    lineage: RuntimeLineageContract
    replay_fingerprint: str
    replay_inputs: dict[str, str] = Field(default_factory=dict)
    deterministic_ready: bool = False
    classification: Literal["PASS", "FAIL_CLOSED"] = "FAIL_CLOSED"
    fail_closed_reasons: list[str] = Field(default_factory=list)


class DeterministicCacheSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_name: str = "deterministic_cache_schema"
    schema_version: str = "1.0"
    cache_key: str
    lineage_id: str
    producer: str
    artifact_paths: list[str] = Field(default_factory=list)
    dependency_fingerprints: dict[str, str] = Field(default_factory=dict)
    cache_valid: bool = False


def build_lineage(*, target_id: str, session_id: str, parent_lineage_id: str = "") -> RuntimeLineageContract:
    lineage_id = deterministic_uuid(f"{target_id}:{session_id}:{parent_lineage_id or 'root'}")
    return RuntimeLineageContract(
        lineage_id=lineage_id,
        session_id=str(session_id),
        target_id=str(target_id),
        parent_lineage_id=str(parent_lineage_id),
    )


def replay_fingerprint_from_inputs(inputs: dict[str, str]) -> str:
    return stable_sha256({"inputs": dict(sorted(inputs.items()))})
