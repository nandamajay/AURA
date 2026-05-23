"""Deterministic event replay engine for AURA Cognition Bus."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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


class AURAEventReplayEngine:
    """Reconstruct agent cognition sync state from persisted event stream only."""

    def __init__(
        self,
        *,
        lineage_path: str | Path,
        sync_state_path: str | Path | None = None,
    ):
        self._lineage_path = Path(lineage_path)
        self._sync_state_path = Path(sync_state_path) if sync_state_path else None

    def reconstruct(self) -> dict[str, Any]:
        lineage = _load_json_if_exists(self._lineage_path)
        events = _coerce_list(lineage.get("events"))
        events_sorted = sorted(
            [_coerce_dict(item) for item in events],
            key=lambda x: int(x.get("sequence", 0) or 0),
        )

        agent_sync: dict[str, Any] = {}
        category_counts: dict[str, int] = {}
        correlation_index: dict[str, list[str]] = {}
        lineage_index: dict[str, list[str]] = {}

        ordered_ids: list[str] = []
        for event in events_sorted:
            metadata = _coerce_dict(event.get("metadata"))
            lifecycle = _coerce_dict(event.get("lifecycle"))
            state = str(lifecycle.get("state", ""))

            # Replay state is reconstructed from persisted stream content.
            if state not in {"persisted", "replayed"}:
                continue

            event_id = str(event.get("event_id", ""))
            ordered_ids.append(event_id)
            agent = str(metadata.get("originating_agent", "")).strip()
            category = str(event.get("category", "")).strip()
            replay_correlation_id = str(metadata.get("replay_correlation_id", "")).strip()
            cognition_lineage_id = str(metadata.get("cognition_lineage_id", "")).strip()

            if replay_correlation_id:
                correlation_index.setdefault(replay_correlation_id, []).append(event_id)
            if cognition_lineage_id:
                lineage_index.setdefault(cognition_lineage_id, []).append(event_id)

            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

            if not agent:
                continue
            entry = agent_sync.setdefault(
                agent,
                {
                    "agent": agent,
                    "events_replayed": 0,
                    "last_event_id": "",
                    "last_sequence": 0,
                    "last_category": "",
                    "last_lifecycle_state": "",
                    "last_timestamp": "",
                    "event_categories": {},
                },
            )
            per_category = _coerce_dict(entry.get("event_categories"))
            per_category[category] = int(per_category.get(category, 0)) + 1
            entry["event_categories"] = per_category
            entry["events_replayed"] = int(entry.get("events_replayed", 0)) + 1
            entry["last_event_id"] = event_id
            entry["last_sequence"] = int(event.get("sequence", 0) or 0)
            entry["last_category"] = category
            entry["last_lifecycle_state"] = state
            entry["last_timestamp"] = str(metadata.get("timestamp", ""))

        replay_fingerprint = hashlib.sha256("|".join(ordered_ids).encode("utf-8")).hexdigest()
        result = {
            "schema_version": "1.0",
            "reconstructed_from_stream_only": True,
            "lineage_path": str(self._lineage_path.resolve()),
            "event_count": len(events_sorted),
            "replay_event_count": len(ordered_ids),
            "category_counts": category_counts,
            "agent_sync_state": agent_sync,
            "replay_correlation_index": correlation_index,
            "cognition_lineage_index": lineage_index,
            "deterministic_replay_fingerprint": replay_fingerprint,
            "updated_at": _utc_now_iso(),
        }

        if self._sync_state_path is not None:
            _save_json(self._sync_state_path, result)

        return result
