"""AURA Cognition Bus for deterministic inter-agent synchronization.

Agents communicate through structured cognition events that are persisted,
validated, replayable, and fail-closed by default.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

EVENT_CATEGORIES: tuple[str, ...] = (
    "runtime",
    "topology",
    "governance",
    "regression",
    "persistence",
    "transport",
)

EVENT_LIFECYCLE: tuple[str, ...] = (
    "emitted",
    "acknowledged",
    "correlated",
    "persisted",
    "replayed",
)

GOVERNANCE_CLASSIFICATIONS: tuple[str, ...] = (
    "FAIL_CLOSED",
    "GOVERNED_APPROVED",
    "ADVISORY_ONLY",
    "REJECTED",
    "QUARANTINED",
)

_LIFECYCLE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "emitted": ("acknowledged",),
    "acknowledged": ("correlated",),
    "correlated": ("persisted",),
    "persisted": ("replayed",),
    "replayed": (),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _stable_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


class AURACognitionBus:
    """Registry-first deterministic cognition event bus with fail-closed posture."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        lineage_path: str | Path | None = None,
        agent_sync_state_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ):
        self._output_dir = Path(output_dir)
        self._lineage_path = Path(lineage_path) if lineage_path else self._output_dir / "aura_event_lineage.json"
        self._agent_sync_state_path = (
            Path(agent_sync_state_path) if agent_sync_state_path else self._output_dir / "aura_agent_sync_state.json"
        )
        self._schema_path = Path(schema_path) if schema_path else self._output_dir / "aura_event_schema.json"

        self._events: list[dict[str, Any]] = []
        self._quarantine: list[dict[str, Any]] = []
        self._next_sequence: int = 1
        self._confidence_model: dict[str, Any] = {
            "schema_version": "1.0",
            "agent_confidence": {},
            "category_confidence": {},
            "propagation_formula": "weighted_avg(confidence * lifecycle_weight * governance_multiplier)",
            "updated_at": _utc_now_iso(),
        }

        self._bootstrap_from_lineage()
        self.persist_schema()
        self.persist_lineage()
        self.persist_agent_sync_state()

    @property
    def event_schema(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "required_fields": [
                "event_id",
                "sequence",
                "category",
                "event_name",
                "payload",
                "metadata",
                "lifecycle",
            ],
            "category_enum": list(EVENT_CATEGORIES),
            "lifecycle_enum": list(EVENT_LIFECYCLE),
            "governance_classification_enum": list(GOVERNANCE_CLASSIFICATIONS),
            "metadata_fields": {
                "timestamp": "iso8601",
                "originating_agent": "string",
                "target_agent": "string_optional",
                "confidence": "float_0_to_1",
                "evidence_references": "list[string]",
                "cognition_lineage_id": "string",
                "replay_correlation_id": "string",
                "governance_classification": "enum",
            },
            "lifecycle_transition_rules": {
                state: list(next_states)
                for state, next_states in _LIFECYCLE_TRANSITIONS.items()
            },
            "fail_closed": True,
            "deterministic_ordering_required": True,
            "updated_at": _utc_now_iso(),
        }

    def _bootstrap_from_lineage(self) -> None:
        payload = _load_json_if_exists(self._lineage_path)
        self._events = _coerce_list(payload.get("events"))
        self._quarantine = _coerce_list(payload.get("quarantine"))
        confidence = _coerce_dict(payload.get("confidence_propagation"))
        if confidence:
            self._confidence_model = confidence

        max_sequence = 0
        for event in self._events:
            seq = int(_coerce_dict(event).get("sequence", 0) or 0)
            max_sequence = max(max_sequence, seq)
        self._next_sequence = max_sequence + 1

    def persist_schema(self) -> None:
        _save_json(self._schema_path, self.event_schema)

    def _reject_and_quarantine(self, reason: str, raw_event: Mapping[str, Any]) -> None:
        quarantine_entry = {
            "quarantine_id": _stable_hash(
                {
                    "reason": reason,
                    "raw_event": dict(raw_event),
                    "at": _utc_now_iso(),
                }
            ),
            "reason": reason,
            "raw_event": dict(raw_event),
            "timestamp": _utc_now_iso(),
        }
        self._quarantine.append(quarantine_entry)
        self._quarantine = self._quarantine[-1000:]
        self.persist_lineage()
        self.persist_agent_sync_state()
        raise PermissionError(f"fail_closed_event_rejected:{reason}")

    def _validate_metadata(self, metadata: Mapping[str, Any], raw_event: Mapping[str, Any]) -> None:
        category = str(raw_event.get("category", "")).strip()
        event_name = str(raw_event.get("event_name", "")).strip()
        if category not in EVENT_CATEGORIES:
            self._reject_and_quarantine("unsupported_category", raw_event)
        if not event_name:
            self._reject_and_quarantine("missing_event_name", raw_event)

        originating_agent = str(metadata.get("originating_agent", "")).strip()
        if not originating_agent:
            self._reject_and_quarantine("missing_originating_agent", raw_event)

        governance_classification = str(metadata.get("governance_classification", "")).strip()
        if governance_classification not in GOVERNANCE_CLASSIFICATIONS:
            self._reject_and_quarantine("unsupported_governance_classification", raw_event)

        try:
            confidence = float(metadata.get("confidence", 0.0))
        except Exception:
            self._reject_and_quarantine("invalid_confidence_type", raw_event)
            return
        if confidence < 0.0 or confidence > 1.0:
            self._reject_and_quarantine("confidence_out_of_range", raw_event)

    def emit_event(
        self,
        *,
        category: str,
        event_name: str,
        originating_agent: str,
        payload: Mapping[str, Any],
        target_agent: str | None = None,
        confidence: float = 0.0,
        evidence_references: list[str] | None = None,
        cognition_lineage_id: str = "",
        replay_correlation_id: str = "",
        governance_classification: str = "ADVISORY_ONLY",
    ) -> dict[str, Any]:
        metadata = {
            "timestamp": _utc_now_iso(),
            "originating_agent": str(originating_agent),
            "target_agent": str(target_agent or ""),
            "confidence": float(confidence),
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
            "cognition_lineage_id": str(cognition_lineage_id),
            "replay_correlation_id": str(replay_correlation_id),
            "governance_classification": str(governance_classification),
        }
        raw_event = {
            "category": str(category),
            "event_name": str(event_name),
            "payload": dict(payload),
            "metadata": metadata,
        }
        self._validate_metadata(metadata, raw_event)

        sequence = self._next_sequence
        event_id = _stable_hash(
            {
                "sequence": sequence,
                "category": category,
                "event_name": event_name,
                "originating_agent": metadata["originating_agent"],
                "target_agent": metadata["target_agent"],
                "payload": dict(payload),
                "replay_correlation_id": metadata["replay_correlation_id"],
            }
        )
        event = {
            "event_id": event_id,
            "sequence": sequence,
            "category": str(category),
            "event_name": str(event_name),
            "payload": dict(payload),
            "metadata": metadata,
            "lifecycle": {
                "state": "emitted",
                "history": [
                    {
                        "state": "emitted",
                        "timestamp": _utc_now_iso(),
                        "actor": "aura_cognition_bus",
                    }
                ],
            },
        }

        self._events.append(event)
        self._events = self._events[-5000:]
        self._next_sequence += 1
        self._update_confidence(event, lifecycle_state="emitted")
        self.persist_lineage()
        self.persist_agent_sync_state()
        return event

    def _event_index(self, event_id: str) -> int:
        for idx, event in enumerate(self._events):
            if str(_coerce_dict(event).get("event_id", "")) == event_id:
                return idx
        self._reject_and_quarantine("unknown_event_id", {"event_id": event_id})
        return -1

    def _advance_lifecycle(
        self,
        *,
        event_id: str,
        next_state: str,
        actor: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if next_state not in EVENT_LIFECYCLE:
            self._reject_and_quarantine("invalid_lifecycle_state", {"event_id": event_id, "next_state": next_state})

        idx = self._event_index(event_id)
        event = _coerce_dict(self._events[idx])
        lifecycle = _coerce_dict(event.get("lifecycle"))
        current_state = str(lifecycle.get("state", "emitted"))
        allowed_next = _LIFECYCLE_TRANSITIONS.get(current_state, ())
        if next_state not in allowed_next:
            self._reject_and_quarantine(
                "invalid_lifecycle_transition",
                {
                    "event_id": event_id,
                    "current_state": current_state,
                    "next_state": next_state,
                    "allowed": list(allowed_next),
                },
            )

        history = _coerce_list(lifecycle.get("history"))
        history.append(
            {
                "state": next_state,
                "timestamp": _utc_now_iso(),
                "actor": str(actor),
                "details": dict(details or {}),
            }
        )
        lifecycle["state"] = next_state
        lifecycle["history"] = history
        event["lifecycle"] = lifecycle
        self._events[idx] = event

        self._update_confidence(event, lifecycle_state=next_state)
        self.persist_lineage()
        self.persist_agent_sync_state()
        return event

    def acknowledge_event(self, event_id: str, *, actor: str) -> dict[str, Any]:
        return self._advance_lifecycle(event_id=event_id, next_state="acknowledged", actor=actor)

    def correlate_event(
        self,
        event_id: str,
        *,
        actor: str,
        correlated_event_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._advance_lifecycle(
            event_id=event_id,
            next_state="correlated",
            actor=actor,
            details={"correlated_event_ids": [str(item) for item in (correlated_event_ids or [])]},
        )

    def persist_event(self, event_id: str, *, actor: str) -> dict[str, Any]:
        return self._advance_lifecycle(event_id=event_id, next_state="persisted", actor=actor)

    def replay_event(self, event_id: str, *, actor: str) -> dict[str, Any]:
        return self._advance_lifecycle(event_id=event_id, next_state="replayed", actor=actor)

    def process_event(
        self,
        *,
        category: str,
        event_name: str,
        originating_agent: str,
        payload: Mapping[str, Any],
        target_agent: str | None = None,
        confidence: float = 0.0,
        evidence_references: list[str] | None = None,
        cognition_lineage_id: str = "",
        replay_correlation_id: str = "",
        governance_classification: str = "ADVISORY_ONLY",
        correlated_event_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        event = self.emit_event(
            category=category,
            event_name=event_name,
            originating_agent=originating_agent,
            payload=payload,
            target_agent=target_agent,
            confidence=confidence,
            evidence_references=evidence_references,
            cognition_lineage_id=cognition_lineage_id,
            replay_correlation_id=replay_correlation_id,
            governance_classification=governance_classification,
        )
        event_id = str(event.get("event_id", ""))
        self.acknowledge_event(event_id, actor=originating_agent)
        self.correlate_event(
            event_id,
            actor=originating_agent,
            correlated_event_ids=correlated_event_ids,
        )
        self.persist_event(event_id, actor="aura_cognition_bus")
        return _coerce_dict(self._events[self._event_index(event_id)])

    def replay_persisted_events(self, *, actor: str = "aura_event_replay_engine") -> list[str]:
        replayed_ids: list[str] = []
        for event in list(self._events):
            event_id = str(_coerce_dict(event).get("event_id", ""))
            lifecycle_state = str(_coerce_dict(event.get("lifecycle")).get("state", ""))
            if lifecycle_state == "persisted":
                self.replay_event(event_id, actor=actor)
                replayed_ids.append(event_id)
        return replayed_ids

    def _update_confidence(self, event: Mapping[str, Any], *, lifecycle_state: str) -> None:
        metadata = _coerce_dict(event.get("metadata"))
        category = str(event.get("category", "")).strip()
        agent = str(metadata.get("originating_agent", "")).strip()
        base_confidence = float(metadata.get("confidence", 0.0) or 0.0)

        lifecycle_weight = {
            "emitted": 0.25,
            "acknowledged": 0.50,
            "correlated": 0.75,
            "persisted": 1.00,
            "replayed": 1.00,
        }.get(lifecycle_state, 0.0)

        governance_multiplier = {
            "FAIL_CLOSED": 1.00,
            "GOVERNED_APPROVED": 1.00,
            "ADVISORY_ONLY": 0.90,
            "REJECTED": 0.00,
            "QUARANTINED": 0.20,
        }.get(str(metadata.get("governance_classification", "ADVISORY_ONLY")), 0.0)

        effective = round(base_confidence * lifecycle_weight * governance_multiplier, 6)

        model = self._confidence_model
        agent_conf = _coerce_dict(model.get("agent_confidence"))
        category_conf = _coerce_dict(model.get("category_confidence"))

        if agent:
            item = _coerce_dict(agent_conf.get(agent))
            count = int(item.get("event_count", 0))
            score = float(item.get("score", 0.0))
            next_score = round(((score * count) + effective) / (count + 1), 6)
            agent_conf[agent] = {
                "score": next_score,
                "event_count": count + 1,
                "last_event_id": str(event.get("event_id", "")),
                "updated_at": _utc_now_iso(),
            }

        if category:
            c_item = _coerce_dict(category_conf.get(category))
            c_count = int(c_item.get("event_count", 0))
            c_score = float(c_item.get("score", 0.0))
            c_next_score = round(((c_score * c_count) + effective) / (c_count + 1), 6)
            category_conf[category] = {
                "score": c_next_score,
                "event_count": c_count + 1,
                "updated_at": _utc_now_iso(),
            }

        model["agent_confidence"] = agent_conf
        model["category_confidence"] = category_conf
        model["updated_at"] = _utc_now_iso()
        self._confidence_model = model

    def validate_ordering(self) -> dict[str, Any]:
        errors: list[str] = []
        last_sequence = 0
        seen: set[int] = set()
        for event in self._events:
            item = _coerce_dict(event)
            sequence = int(item.get("sequence", 0) or 0)
            if sequence <= 0:
                errors.append("invalid_sequence_non_positive")
                continue
            if sequence in seen:
                errors.append(f"duplicate_sequence:{sequence}")
            if sequence <= last_sequence:
                errors.append(f"out_of_order_sequence:{sequence}")
            seen.add(sequence)
            last_sequence = max(last_sequence, sequence)

            lifecycle = _coerce_dict(item.get("lifecycle"))
            history = _coerce_list(lifecycle.get("history"))
            previous_idx = -1
            for step in history:
                state = str(_coerce_dict(step).get("state", ""))
                if state not in EVENT_LIFECYCLE:
                    errors.append(f"unknown_lifecycle_state:{state}")
                    continue
                current_idx = EVENT_LIFECYCLE.index(state)
                if current_idx < previous_idx:
                    errors.append(f"lifecycle_out_of_order:{item.get('event_id', '')}:{state}")
                previous_idx = current_idx

        return {
            "valid": not errors,
            "errors": errors,
            "event_count": len(self._events),
            "quarantine_count": len(self._quarantine),
            "updated_at": _utc_now_iso(),
        }

    def build_agent_sync_state(self) -> dict[str, Any]:
        sync: dict[str, dict[str, Any]] = {}
        for event in self._events:
            item = _coerce_dict(event)
            metadata = _coerce_dict(item.get("metadata"))
            agent = str(metadata.get("originating_agent", "")).strip()
            if not agent:
                continue
            entry = sync.setdefault(
                agent,
                {
                    "agent": agent,
                    "events_processed": 0,
                    "last_event_id": "",
                    "last_sequence": 0,
                    "last_category": "",
                    "last_lifecycle_state": "",
                    "last_timestamp": "",
                    "replay_correlation_id": "",
                    "event_categories": {},
                },
            )
            category = str(item.get("category", ""))
            categories = _coerce_dict(entry.get("event_categories"))
            categories[category] = int(categories.get(category, 0)) + 1
            entry["event_categories"] = categories
            entry["events_processed"] = int(entry.get("events_processed", 0)) + 1
            entry["last_event_id"] = str(item.get("event_id", ""))
            entry["last_sequence"] = int(item.get("sequence", 0) or 0)
            entry["last_category"] = category
            entry["last_lifecycle_state"] = str(_coerce_dict(item.get("lifecycle")).get("state", ""))
            entry["last_timestamp"] = str(metadata.get("timestamp", ""))
            entry["replay_correlation_id"] = str(metadata.get("replay_correlation_id", ""))

        agent_confidence = _coerce_dict(self._confidence_model.get("agent_confidence"))
        for agent, entry in sync.items():
            entry["confidence"] = float(_coerce_dict(agent_confidence.get(agent)).get("score", 0.0))

        return {
            "schema_version": "1.0",
            "fail_closed": True,
            "ordering_validation": self.validate_ordering(),
            "agent_sync": sync,
            "quarantine_count": len(self._quarantine),
            "event_count": len(self._events),
            "updated_at": _utc_now_iso(),
        }

    def persist_agent_sync_state(self) -> dict[str, Any]:
        sync_state = self.build_agent_sync_state()
        _save_json(self._agent_sync_state_path, sync_state)
        return sync_state

    def build_lineage_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "event_schema_path": str(self._schema_path.resolve()),
            "fail_closed": True,
            "event_categories": list(EVENT_CATEGORIES),
            "event_lifecycle": list(EVENT_LIFECYCLE),
            "events": self._events,
            "quarantine": self._quarantine,
            "ordering_validation": self.validate_ordering(),
            "confidence_propagation": self._confidence_model,
            "updated_at": _utc_now_iso(),
        }

    def persist_lineage(self) -> dict[str, Any]:
        payload = self.build_lineage_payload()
        _save_json(self._lineage_path, payload)
        return payload

    def get_events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def get_lineage(self) -> dict[str, Any]:
        return self.build_lineage_payload()

    def get_confidence_propagation_model(self) -> dict[str, Any]:
        model = dict(self._confidence_model)
        model["updated_at"] = _utc_now_iso()
        return model

    def observe_runtime(
        self,
        *,
        event_name: str,
        originating_agent: str,
        payload: Mapping[str, Any],
        target_agent: str | None = None,
        confidence: float = 0.0,
        evidence_references: list[str] | None = None,
        cognition_lineage_id: str = "",
        replay_correlation_id: str = "",
        governance_classification: str = "ADVISORY_ONLY",
    ) -> dict[str, Any]:
        return self.process_event(
            category="runtime",
            event_name=event_name,
            originating_agent=originating_agent,
            payload=payload,
            target_agent=target_agent,
            confidence=confidence,
            evidence_references=evidence_references,
            cognition_lineage_id=cognition_lineage_id,
            replay_correlation_id=replay_correlation_id,
            governance_classification=governance_classification,
        )

    def observe_topology(self, **kwargs: Any) -> dict[str, Any]:
        return self.process_event(category="topology", **kwargs)

    def observe_regression(self, **kwargs: Any) -> dict[str, Any]:
        return self.process_event(category="regression", **kwargs)

    def observe_governance(self, **kwargs: Any) -> dict[str, Any]:
        return self.process_event(category="governance", **kwargs)

    def observe_transport(self, **kwargs: Any) -> dict[str, Any]:
        return self.process_event(category="transport", **kwargs)

    def observe_persistence(self, **kwargs: Any) -> dict[str, Any]:
        return self.process_event(category="persistence", **kwargs)

    def build_cognition_bus_architecture(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "name": "AURA_Cognition_Bus",
            "coordination_model": "registry_first_event_stream",
            "fail_closed": True,
            "categories": list(EVENT_CATEGORIES),
            "lifecycle": list(EVENT_LIFECYCLE),
            "observers": [
                "runtime_observer",
                "topology_observer",
                "regression_observer",
                "governance_observer",
            ],
            "artifacts": {
                "event_schema": str(self._schema_path.resolve()),
                "event_lineage": str(self._lineage_path.resolve()),
                "agent_sync_state": str(self._agent_sync_state_path.resolve()),
            },
            "updated_at": _utc_now_iso(),
        }

    def build_event_flow_graph(self) -> dict[str, Any]:
        nodes: list[dict[str, str]] = []
        edges: list[dict[str, str]] = []

        for category in EVENT_CATEGORIES:
            nodes.append({"id": f"category:{category}", "kind": "category", "label": category})

        seen_agents: set[str] = set()
        for event in self._events:
            item = _coerce_dict(event)
            metadata = _coerce_dict(item.get("metadata"))
            origin = str(metadata.get("originating_agent", "")).strip()
            target = str(metadata.get("target_agent", "")).strip()
            event_id = str(item.get("event_id", ""))
            category = str(item.get("category", ""))
            if origin and origin not in seen_agents:
                nodes.append({"id": f"agent:{origin}", "kind": "agent", "label": origin})
                seen_agents.add(origin)
            if target and target not in seen_agents:
                nodes.append({"id": f"agent:{target}", "kind": "agent", "label": target})
                seen_agents.add(target)

            nodes.append({"id": f"event:{event_id}", "kind": "event", "label": str(item.get("event_name", ""))})
            edges.append({"from": f"category:{category}", "to": f"event:{event_id}", "relation": "contains"})
            if origin:
                edges.append({"from": f"agent:{origin}", "to": f"event:{event_id}", "relation": "emits"})
            if target:
                edges.append({"from": f"event:{event_id}", "to": f"agent:{target}", "relation": "targets"})

        dedup_nodes = {node["id"]: node for node in nodes}
        return {
            "schema_version": "1.0",
            "nodes": list(dedup_nodes.values()),
            "edges": edges,
            "updated_at": _utc_now_iso(),
        }

    def build_replay_lifecycle_graph(self) -> dict[str, Any]:
        edges = []
        for state, next_states in _LIFECYCLE_TRANSITIONS.items():
            for nxt in next_states:
                edges.append({"from": state, "to": nxt, "relation": "allowed_transition"})

        return {
            "schema_version": "1.0",
            "nodes": [{"id": state, "kind": "lifecycle_state", "label": state} for state in EVENT_LIFECYCLE],
            "edges": edges,
            "deterministic_replay_requires": ["ordered_sequence", "persisted_event_stream", "fail_closed_validation"],
            "updated_at": _utc_now_iso(),
        }

    def export_bus_artifacts(self) -> dict[str, str]:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        schema_payload = self.event_schema
        line_payload = self.persist_lineage()
        sync_payload = self.persist_agent_sync_state()
        architecture_payload = self.build_cognition_bus_architecture()
        flow_payload = self.build_event_flow_graph()
        replay_payload = self.build_replay_lifecycle_graph()
        confidence_payload = self.get_confidence_propagation_model()

        schema_path = self._output_dir / "aura_event_schema.json"
        persistence_schema_path = self._output_dir / "aura_event_persistence_schema.json"
        lineage_path = self._lineage_path
        sync_path = self._agent_sync_state_path
        architecture_path = self._output_dir / "aura_cognition_bus_architecture.json"
        flow_path = self._output_dir / "aura_event_flow_graph.json"
        replay_path = self._output_dir / "aura_replay_lifecycle_graph.json"
        confidence_path = self._output_dir / "aura_confidence_propagation_model.json"

        _save_json(schema_path, schema_payload)
        _save_json(persistence_schema_path, schema_payload)
        _save_json(lineage_path, line_payload)
        _save_json(sync_path, sync_payload)
        _save_json(architecture_path, architecture_payload)
        _save_json(flow_path, flow_payload)
        _save_json(replay_path, replay_payload)
        _save_json(confidence_path, confidence_payload)

        return {
            "aura_event_schema": str(schema_path.resolve()),
            "aura_event_persistence_schema": str(persistence_schema_path.resolve()),
            "aura_event_lineage": str(lineage_path.resolve()),
            "aura_agent_sync_state": str(sync_path.resolve()),
            "aura_cognition_bus_architecture": str(architecture_path.resolve()),
            "aura_event_flow_graph": str(flow_path.resolve()),
            "aura_replay_lifecycle_graph": str(replay_path.resolve()),
            "aura_confidence_propagation_model": str(confidence_path.resolve()),
        }
