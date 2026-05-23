#!/usr/bin/env python3
"""AURA determinism validator for replay/cognition/topology stability."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.agentization import AURAInternalAgentizationCoordinator  # noqa: E402
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine  # noqa: E402
from aura_sdk.transport.cognitive_persistence import AURACognitionBootLoader  # noqa: E402


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


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _strip_dynamic(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            k = str(key)
            if k in {
                "updated_at",
                "recorded_at",
                "booted_at",
                "created_at",
                "exported_at",
                "modified_at_epoch",
            }:
                continue
            out[k] = _strip_dynamic(item)
        return out
    if isinstance(value, list):
        return [_strip_dynamic(item) for item in value]
    return value


def _majority_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    return round(max(counts.values()) / len(values), 6)


def _semantic_tail_fingerprint(events: list[dict[str, Any]], window: int = 6) -> str:
    tail = events[-max(1, window):]
    normalized = [
        {
            "category": str(item.get("category", "")),
            "source": str(item.get("source", "")),
            "target": str(item.get("target", "")),
            "lifecycle": str(item.get("lifecycle", "")),
        }
        for item in tail
    ]
    return _stable_hash(normalized)


@dataclass(frozen=True)
class SampleResult:
    sample_index: int
    event_ordering_valid: bool
    event_ordering_fingerprint: str
    confidence_fingerprint: str
    topology_fingerprint: str
    replay_state_fingerprint: str
    procedural_memory_fingerprint: str
    baseline_fingerprint: str
    cognition_reconstruction_fingerprint: str


class DeterminismValidator:
    def __init__(
        self,
        *,
        output_dir: Path,
        sample_count: int,
        sleep_seconds: float,
        run_agentization_each_sample: bool,
    ):
        self.output_dir = output_dir
        self.sample_count = max(1, sample_count)
        self.sleep_seconds = max(0.0, sleep_seconds)
        self.run_agentization_each_sample = run_agentization_each_sample

    def _new_coordinator(self) -> AURAInternalAgentizationCoordinator:
        out = self.output_dir
        return AURAInternalAgentizationCoordinator(
            output_dir=out,
            cognition_registry_path=out / "aura_cognition_registry.json",
            phase_state_path=out / "aura_phase_state.json",
            governance_state_path=out / "aura_governance_state.json",
            baseline_registry_path=out / "rb3gen2_audible_baseline_registry.json",
            procedural_memory_path=out / "rb3gen2_procedural_memory.json",
            procedural_lock_path=out / "rb3gen2_procedural_memory_lock.json",
            procedural_route_memory_path=out / "rb3gen2_procedural_route_memory.json",
            runtime_report_path=out / "runtime_capability_report.json",
            artifact_index_path=out / "aura_artifact_index.json",
            portable_snapshot_path=out / "aura_cognition_portable_snapshot.json",
        )

    def _boot_fingerprint(self) -> str:
        out = self.output_dir
        boot = AURACognitionBootLoader(
            registry_path=out / "aura_cognition_registry.json",
            phase_state_path=out / "aura_phase_state.json",
            governance_state_path=out / "aura_governance_state.json",
            output_dir=out,
            runtime_report_path=out / "runtime_capability_report.json",
            baseline_registry_path=out / "rb3gen2_audible_baseline_registry.json",
            procedural_memory_path=out / "rb3gen2_procedural_memory.json",
            procedural_lock_path=out / "rb3gen2_procedural_memory_lock.json",
            procedural_route_memory_path=out / "rb3gen2_procedural_route_memory.json",
        ).boot()
        normalized = {
            "boot_summary": _strip_dynamic(boot.boot_summary),
            "phase_state": _strip_dynamic(boot.phase_state),
            "governance_state": _strip_dynamic(boot.governance_state),
        }
        return _stable_hash(normalized)

    def _sample(self, sample_index: int) -> SampleResult:
        out = self.output_dir
        if self.run_agentization_each_sample:
            coordinator = self._new_coordinator()
            result = coordinator.run_cycle()
            coordinator.export_architecture_artifacts(result)

        lineage = _load_json_if_exists(out / "aura_event_lineage.json")
        confidence = _load_json_if_exists(out / "aura_confidence_propagation_model.json")
        topology_graph = _load_json_if_exists(out / "topology_graph.json")
        route_graph = _load_json_if_exists(out / "runtime_route_graph.json")
        overlay_graph = _load_json_if_exists(out / "overlay_mutation_graph.json")
        procedural_memory = _load_json_if_exists(out / "rb3gen2_procedural_memory.json")
        procedural_lock = _load_json_if_exists(out / "rb3gen2_procedural_memory_lock.json")
        procedural_route = _load_json_if_exists(out / "rb3gen2_procedural_route_memory.json")
        baseline_registry = _load_json_if_exists(out / "rb3gen2_audible_baseline_registry.json")

        replay_state = AURAEventReplayEngine(
            lineage_path=out / "aura_event_lineage.json",
            sync_state_path=out / "aura_agent_sync_state.json",
        ).reconstruct()

        events = []
        for item in lineage.get("events", []):
            if not isinstance(item, dict):
                continue
            events.append(
                {
                    "sequence": int(item.get("sequence", 0) or 0),
                    "event_id": str(item.get("event_id", "")),
                    "category": str(item.get("category", "")),
                    "lifecycle": str(item.get("lifecycle", {}).get("state", "")),
                    "source": str(item.get("metadata", {}).get("originating_agent", "")),
                    "target": str(item.get("metadata", {}).get("target_agent", "")),
                }
            )

        ordering_validation = lineage.get("ordering_validation", {})
        profile = baseline_registry.get("profiles", {}).get("audible_25s_speaker_v1", {})
        replay_semantic = {
            "tail_pattern_fingerprint": _semantic_tail_fingerprint(events, window=6),
            "agent_last_state": {
                agent: {
                    "last_category": str(data.get("last_category", "")),
                    "last_lifecycle_state": str(data.get("last_lifecycle_state", "")),
                }
                for agent, data in sorted(
                    (
                        (k, v)
                        for k, v in replay_state.get("agent_sync_state", {}).items()
                        if isinstance(v, dict)
                    ),
                    key=lambda x: x[0],
                )
            },
        }

        return SampleResult(
            sample_index=sample_index,
            event_ordering_valid=bool(ordering_validation.get("valid", False)),
            event_ordering_fingerprint=_stable_hash(events),
            confidence_fingerprint=_stable_hash(_strip_dynamic(confidence)),
            topology_fingerprint=_stable_hash(
                {
                    "topology_graph": _strip_dynamic(topology_graph),
                    "runtime_route_graph": _strip_dynamic(route_graph),
                    "overlay_mutation_graph": _strip_dynamic(overlay_graph),
                }
            ),
            replay_state_fingerprint=_stable_hash(_strip_dynamic(replay_semantic)),
            procedural_memory_fingerprint=_stable_hash(
                {
                    "memory": _strip_dynamic(procedural_memory),
                    "lock": _strip_dynamic(procedural_lock),
                    "route": _strip_dynamic(procedural_route),
                }
            ),
            baseline_fingerprint=_stable_hash(_strip_dynamic(profile)),
            cognition_reconstruction_fingerprint=self._boot_fingerprint(),
        )

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        samples: list[SampleResult] = []
        for idx in range(self.sample_count):
            samples.append(self._sample(idx + 1))
            if idx + 1 < self.sample_count and self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        event_valid_ratio = round(
            sum(1 for item in samples if item.event_ordering_valid) / len(samples),
            6,
        )
        replay_stability_score = _majority_ratio([s.replay_state_fingerprint for s in samples])
        topology_consistency_score = _majority_ratio([s.topology_fingerprint for s in samples])
        reconstruction_equivalence_score = _majority_ratio(
            [s.cognition_reconstruction_fingerprint for s in samples]
        )

        report = {
            "schema_version": "1.0",
            "validator": "aura_determinism_validator",
            "sample_count": len(samples),
            "event_ordering_stability": {
                "valid_ratio": event_valid_ratio,
                "fingerprint_stability": _majority_ratio([s.event_ordering_fingerprint for s in samples]),
            },
            "confidence_stability": {
                "fingerprint_stability": _majority_ratio([s.confidence_fingerprint for s in samples]),
            },
            "topology_fingerprint_stability": {
                "fingerprint_stability": topology_consistency_score,
            },
            "replay_state_equivalence": {
                "fingerprint_stability": replay_stability_score,
            },
            "procedural_memory_consistency": {
                "fingerprint_stability": _majority_ratio([s.procedural_memory_fingerprint for s in samples]),
            },
            "baseline_equivalence": {
                "fingerprint_stability": _majority_ratio([s.baseline_fingerprint for s in samples]),
            },
            "cognition_reconstruction_equivalence": {
                "fingerprint_stability": reconstruction_equivalence_score,
            },
            "stability_metrics": {
                "replay_stability_score": replay_stability_score,
                "topology_consistency_score": topology_consistency_score,
                "reconstruction_equivalence_score": reconstruction_equivalence_score,
            },
            "samples": [
                {
                    "sample_index": s.sample_index,
                    "event_ordering_valid": s.event_ordering_valid,
                    "event_ordering_fingerprint": s.event_ordering_fingerprint,
                    "confidence_fingerprint": s.confidence_fingerprint,
                    "topology_fingerprint": s.topology_fingerprint,
                    "replay_state_fingerprint": s.replay_state_fingerprint,
                    "procedural_memory_fingerprint": s.procedural_memory_fingerprint,
                    "baseline_fingerprint": s.baseline_fingerprint,
                    "cognition_reconstruction_fingerprint": s.cognition_reconstruction_fingerprint,
                }
                for s in samples
            ],
            "generated_at_epoch": time.time(),
        }
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA determinism validator")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument(
        "--skip-agentization",
        action="store_true",
        help="Do not run agentization per sample; validate current artifacts only.",
    )
    parser.add_argument(
        "--report-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_replay_determinism_report.json",
    )
    args = parser.parse_args()

    validator = DeterminismValidator(
        output_dir=Path(args.output_dir),
        sample_count=args.sample_count,
        sleep_seconds=args.sleep_seconds,
        run_agentization_each_sample=not args.skip_agentization,
    )
    report = validator.run()
    report_path = Path(args.report_path)
    _save_json(report_path, report)

    print(json.dumps({"report": str(report_path.resolve()), **report["stability_metrics"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
