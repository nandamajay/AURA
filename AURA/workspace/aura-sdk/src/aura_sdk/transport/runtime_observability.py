"""Runtime pipeline observability for deterministic governance diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from aura_sdk.transport.deterministic_serialization import stable_sha256


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeObservation:
    event_type: str
    severity: Literal["INFO", "WARN", "ERROR"]
    component: str
    detail: str
    created_at: str


class RuntimeObservabilityCollector:
    """Collect deterministic runtime pipeline observability events."""

    def __init__(self) -> None:
        self._events: list[RuntimeObservation] = []

    def record(
        self,
        *,
        event_type: str,
        severity: Literal["INFO", "WARN", "ERROR"],
        component: str,
        detail: str,
    ) -> None:
        self._events.append(
            RuntimeObservation(
                event_type=str(event_type),
                severity=severity,
                component=str(component),
                detail=str(detail),
                created_at=_utc_now_iso(),
            )
        )

    def as_report(self) -> dict[str, Any]:
        events = [
            {
                "event_type": row.event_type,
                "severity": row.severity,
                "component": row.component,
                "detail": row.detail,
                "created_at": row.created_at,
            }
            for row in self._events
        ]
        error_count = sum(1 for row in self._events if row.severity == "ERROR")
        warning_count = sum(1 for row in self._events if row.severity == "WARN")
        report = {
            "schema_version": "1.0",
            "report_name": "runtime_observability_report",
            "generated_at": _utc_now_iso(),
            "classification": "FAIL_CLOSED" if error_count else "PASS",
            "summary": {
                "event_count": len(events),
                "warning_count": warning_count,
                "error_count": error_count,
            },
            "events": events,
        }
        report["deterministic_fingerprint"] = stable_sha256(
            {
                "classification": report["classification"],
                "summary": report["summary"],
                "events": [
                    {
                        "event_type": row["event_type"],
                        "severity": row["severity"],
                        "component": row["component"],
                        "detail": row["detail"],
                    }
                    for row in events
                ],
            }
        )
        return report
