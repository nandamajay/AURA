#!/usr/bin/env python3
"""AURA event quarantine and fail-closed rejection validation."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus  # noqa: E402


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _expect_rejection(fn) -> tuple[bool, str]:
    try:
        fn()
    except PermissionError as exc:
        return (str(exc).startswith("fail_closed_event_rejected:"), str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return (False, str(exc))
    return (False, "no_rejection")


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA event quarantine validation")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--report-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_event_quarantine_report.json",
    )
    args = parser.parse_args()

    scenarios: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="aura_quarantine_") as tmp:
        root = Path(tmp)

        bus = AURACognitionBus(output_dir=root / "malformed")
        ok, detail = _expect_rejection(
            lambda: bus.emit_event(
                category="runtime",
                event_name="",
                originating_agent="runtime_agent",
                payload={},
                governance_classification="GOVERNED_APPROVED",
            )
        )
        scenarios.append({"scenario": "malformed_event", "passed": ok, "detail": detail})

        bus2 = AURACognitionBus(output_dir=root / "unsupported")
        ok, detail = _expect_rejection(
            lambda: bus2.emit_event(
                category="unsupported",
                event_name="unknown_type",
                originating_agent="runtime_agent",
                payload={},
                governance_classification="GOVERNED_APPROVED",
            )
        )
        scenarios.append({"scenario": "unsupported_event_type", "passed": ok, "detail": detail})

        bus3 = AURACognitionBus(output_dir=root / "invalid_confidence")
        ok, detail = _expect_rejection(
            lambda: bus3.emit_event(
                category="runtime",
                event_name="runtime_validation_state",
                originating_agent="runtime_agent",
                payload={},
                confidence=2.0,
                governance_classification="GOVERNED_APPROVED",
            )
        )
        scenarios.append({"scenario": "invalid_confidence_metadata", "passed": ok, "detail": detail})

        bus4 = AURACognitionBus(output_dir=root / "duplicate_replay")
        event = bus4.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"ok": True},
            confidence=1.0,
            evidence_references=["/tmp/trace.json"],
            replay_correlation_id="dup-replay",
            governance_classification="GOVERNED_APPROVED",
        )
        bus4.replay_event(str(event.get("event_id", "")), actor="aura_event_replay_engine")
        ok, detail = _expect_rejection(
            lambda: bus4.replay_event(str(event.get("event_id", "")), actor="aura_event_replay_engine")
        )
        scenarios.append({"scenario": "duplicated_replay_ids", "passed": ok, "detail": detail})

        bus5 = AURACognitionBus(output_dir=root / "ordering_corruption")
        bus5.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"ok": True},
            confidence=1.0,
            evidence_references=["/tmp/trace.json"],
            governance_classification="GOVERNED_APPROVED",
        )
        # Deliberate corruption to validate deterministic detection.
        bus5._events.append(dict(bus5._events[0]))  # noqa: SLF001
        ordering = bus5.validate_ordering()
        scenarios.append(
            {
                "scenario": "replay_ordering_corruption",
                "passed": bool(not ordering.get("valid", True)),
                "detail": ordering,
            }
        )

        corrupt_dir = root / "lineage_corruption"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "aura_event_lineage.json").write_text("{not-json", encoding="utf-8")
        bus6 = AURACognitionBus(output_dir=corrupt_dir)
        ok, detail = _expect_rejection(
            lambda: bus6.emit_event(
                category="invalid",
                event_name="poison",
                originating_agent="runtime_agent",
                payload={},
                governance_classification="GOVERNED_APPROVED",
            )
        )
        scenarios.append(
            {
                "scenario": "lineage_corruption_then_reject_poison",
                "passed": ok,
                "detail": detail,
                "ordering_after_corruption": bus6.validate_ordering(),
            }
        )

        quarantine_totals = 0
        for folder in root.glob("*"):
            if not folder.is_dir():
                continue
            lineage_path = folder / "aura_event_lineage.json"
            if not lineage_path.exists():
                continue
            try:
                payload = json.loads(lineage_path.read_text(encoding="utf-8"))
                quarantine_totals += len(payload.get("quarantine", [])) if isinstance(payload, dict) else 0
            except Exception:
                continue

    passed = sum(1 for s in scenarios if bool(s.get("passed", False)))
    total = len(scenarios)
    score = round(passed / total, 6) if total else 0.0

    report = {
        "schema_version": "1.0",
        "validator": "aura_event_quarantine_tests",
        "scenarios": scenarios,
        "summary": {
            "passed": passed,
            "total": total,
            "quarantine_total": quarantine_totals,
            "event_quarantine_score": score,
        },
        "generated_at_epoch": time.time(),
    }

    report_path = Path(args.report_path)
    _save_json(report_path, report)
    print(
        json.dumps(
            {
                "report": str(report_path.resolve()),
                "event_quarantine_score": score,
                "quarantine_total": quarantine_totals,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
