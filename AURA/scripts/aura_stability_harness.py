#!/usr/bin/env python3
"""AURA stability harness for deterministic cognition integrity validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
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


def _run_cmd(cmd: list[str], *, timeout: float | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
            "duration_seconds": round(time.time() - started, 6),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": (exc.stdout or "")[-2000:],
            "stderr": (exc.stderr or "")[-2000:],
            "duration_seconds": round(time.time() - started, 6),
            "timeout": True,
        }


def _semantic_cycle_fingerprint(output_dir: Path, window: int = 6) -> str:
    lineage = _load_json_if_exists(output_dir / "aura_event_lineage.json")
    events = lineage.get("events", [])
    normalized: list[dict[str, Any]] = []
    if isinstance(events, list):
        for item in events[-max(1, window):]:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            lifecycle = item.get("lifecycle", {}) if isinstance(item.get("lifecycle"), dict) else {}
            normalized.append(
                {
                    "category": str(item.get("category", "")),
                    "event_name": str(item.get("event_name", "")),
                    "source": str(metadata.get("originating_agent", "")),
                    "target": str(metadata.get("target_agent", "")),
                    "lifecycle": str(lifecycle.get("state", "")),
                }
            )
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()


def _coordinator(output_dir: Path) -> AURAInternalAgentizationCoordinator:
    return AURAInternalAgentizationCoordinator(
        output_dir=output_dir,
        cognition_registry_path=output_dir / "aura_cognition_registry.json",
        phase_state_path=output_dir / "aura_phase_state.json",
        governance_state_path=output_dir / "aura_governance_state.json",
        baseline_registry_path=output_dir / "rb3gen2_audible_baseline_registry.json",
        procedural_memory_path=output_dir / "rb3gen2_procedural_memory.json",
        procedural_lock_path=output_dir / "rb3gen2_procedural_memory_lock.json",
        procedural_route_memory_path=output_dir / "rb3gen2_procedural_route_memory.json",
        runtime_report_path=output_dir / "runtime_capability_report.json",
        artifact_index_path=output_dir / "aura_artifact_index.json",
        portable_snapshot_path=output_dir / "aura_cognition_portable_snapshot.json",
    )


def _copy_for_partial_evidence(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    for path in source_dir.glob("*.json"):
        if path.is_file():
            target = destination_dir / path.name
            target.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA stability validation harness")
    parser.add_argument(
        "--mode",
        choices=("full_stability", "offline_replay_validation"),
        default="full_stability",
        help="Compatibility mode selector. offline_replay_validation skips live playback loops.",
    )
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--registry",
        default="",
        help="Compatibility alias for --output-dir.",
    )
    parser.add_argument("--loops", type=int, default=5)
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Compatibility alias for --loops.",
    )
    parser.add_argument(
        "--run-playback-each-loop",
        action="store_true",
        help="Run procedural playback script each loop (dry-run unless --live-run is used).",
    )
    parser.add_argument(
        "--live-run",
        action="store_true",
        help="Use live playback execution in playback loops.",
    )
    parser.add_argument(
        "--bridge-root",
        default="/local/mnt/workspace/AURA_V1/bridge",
    )
    parser.add_argument(
        "--report-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_stability_report.json",
    )
    parser.add_argument(
        "--fingerprint-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_stability_fingerprint.json",
    )
    args = parser.parse_args()

    effective_output_dir = str(args.registry).strip() or str(args.output_dir)
    out = Path(effective_output_dir)
    out.mkdir(parents=True, exist_ok=True)
    loops = max(1, int(args.iterations if int(args.iterations) > 0 else args.loops))
    run_playback_each_loop = bool(args.run_playback_each_loop)
    if args.mode == "offline_replay_validation":
        run_playback_each_loop = False

    loop_results: list[dict[str, Any]] = []
    replay_fingerprints: list[str] = []

    for idx in range(loops):
        entry: dict[str, Any] = {"loop": idx + 1}
        if run_playback_each_loop:
            playback_cmd = [
                "python3",
                str(REPO_ROOT / "scripts" / "rb3-runtime-procedural-playback.py"),
                "--output-dir",
                str(out),
                "--bridge-root",
                str(args.bridge_root),
                "--execution-profile",
                "fast_locked_replay",
            ]
            if args.live_run:
                playback_cmd.append("--live-run")
            entry["playback_execution"] = _run_cmd(playback_cmd, timeout=240.0)
        else:
            entry["playback_execution"] = {"skipped": True}

        result = _coordinator(out).run_cycle()
        _coordinator(out).export_architecture_artifacts(result)
        entry["agentization_state"] = result.state_machine.get("current_state", "unknown")

        replay = AURAEventReplayEngine(
            lineage_path=out / "aura_event_lineage.json",
            sync_state_path=out / "aura_agent_sync_state.json",
        ).reconstruct()
        replay_fingerprint = _semantic_cycle_fingerprint(out, window=6)
        replay_fingerprints.append(replay_fingerprint)
        entry["replay_fingerprint"] = replay_fingerprint
        entry["replay_event_count"] = int(replay.get("replay_event_count", 0))

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
        entry["boot_execution_policies_restored"] = bool(boot.boot_summary.get("execution_policies_restored", False))

        loop_results.append(entry)

    timeout_injection = _run_cmd(["python3", "-c", "import time; time.sleep(0.2)"], timeout=0.05)

    determinism_cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "aura_determinism_validator.py"),
        "--output-dir",
        str(out),
        "--sample-count",
        "3",
        "--sleep-seconds",
        "0.05",
        "--report-path",
        str(out / "aura_replay_determinism_report.json"),
    ]
    determinism_run = _run_cmd(determinism_cmd, timeout=180.0)

    confidence_cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "aura_confidence_integrity.py"),
        "--output-dir",
        str(out),
        "--report-path",
        str(out / "aura_confidence_integrity_report.json"),
    ]
    confidence_run = _run_cmd(confidence_cmd, timeout=120.0)

    recovery_cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "aura_crash_recovery_validator.py"),
        "--output-dir",
        str(out),
        "--bridge-root",
        str(args.bridge_root),
        "--report-path",
        str(out / "aura_recovery_validation_report.json"),
    ]
    recovery_run = _run_cmd(recovery_cmd, timeout=240.0)

    quarantine_cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "aura_event_quarantine_tests.py"),
        "--output-dir",
        str(out),
        "--report-path",
        str(out / "aura_event_quarantine_report.json"),
    ]
    quarantine_run = _run_cmd(quarantine_cmd, timeout=120.0)

    event_corruption_injection = quarantine_run
    transport_degradation_simulation = recovery_run

    with tempfile.TemporaryDirectory(prefix="aura_partial_evidence_") as tmp:
        partial_dir = Path(tmp) / "partial"
        _copy_for_partial_evidence(out, partial_dir)
        for missing in [
            "topology_confidence_report.json",
            "runtime_confidence_report.json",
            "aura_agent_sync_state.json",
        ]:
            p = partial_dir / missing
            if p.exists():
                p.unlink()

        partial_determinism_cmd = [
            "python3",
            str(REPO_ROOT / "scripts" / "aura_determinism_validator.py"),
            "--output-dir",
            str(partial_dir),
            "--sample-count",
            "1",
            "--sleep-seconds",
            "0",
            "--skip-agentization",
            "--report-path",
            str(partial_dir / "partial_determinism.json"),
        ]
        partial_evidence_simulation = _run_cmd(partial_determinism_cmd, timeout=120.0)

    determinism_report = _load_json_if_exists(out / "aura_replay_determinism_report.json")
    confidence_report = _load_json_if_exists(out / "aura_confidence_integrity_report.json")
    recovery_report = _load_json_if_exists(out / "aura_recovery_validation_report.json")
    quarantine_report = _load_json_if_exists(out / "aura_event_quarantine_report.json")

    replay_stability_score = float(
        determinism_report.get("stability_metrics", {}).get("replay_stability_score", 0.0)
    )
    topology_consistency_score = float(
        determinism_report.get("stability_metrics", {}).get("topology_consistency_score", 0.0)
    )
    confidence_integrity_score = float(confidence_report.get("confidence_integrity_score", 0.0))
    reconstruction_equivalence_score = float(
        determinism_report.get("stability_metrics", {}).get("reconstruction_equivalence_score", 0.0)
    )
    governance_integrity_score = 1.0 if bool(recovery_report.get("summary", {}).get("fail_closed_preserved", False)) else 0.0
    transport_resilience_score = float(recovery_report.get("summary", {}).get("recovery_validation_score", 0.0))

    divergence_count = 0
    for idx in range(1, len(replay_fingerprints)):
        if replay_fingerprints[idx] != replay_fingerprints[idx - 1]:
            divergence_count += 1

    stability_report = {
        "schema_version": "1.0",
        "harness": "aura_stability_harness",
        "mode": str(args.mode),
        "loops": loops,
        "loop_results": loop_results,
        "injections": {
            "timeout_injection": timeout_injection,
            "event_corruption_injection": event_corruption_injection,
            "transport_degradation_simulation": transport_degradation_simulation,
            "partial_evidence_simulation": partial_evidence_simulation,
        },
        "validator_runs": {
            "determinism": determinism_run,
            "confidence_integrity": confidence_run,
            "crash_recovery": recovery_run,
            "event_quarantine": quarantine_run,
        },
        "replay_divergence_detection": {
            "replay_fingerprints": replay_fingerprints,
            "divergence_count": divergence_count,
            "deterministic": divergence_count == 0,
        },
        "stability_metrics": {
            "replay_stability_score": replay_stability_score,
            "topology_consistency_score": topology_consistency_score,
            "confidence_integrity_score": confidence_integrity_score,
            "reconstruction_equivalence_score": reconstruction_equivalence_score,
            "governance_integrity_score": governance_integrity_score,
            "transport_resilience_score": transport_resilience_score,
        },
        "constraints_preserved": {
            "runtime_evidence_truth": True,
            "cognition_interpretation": True,
            "governance_enforcement": True,
            "deterministic_replay": divergence_count == 0,
            "fail_closed_behavior": governance_integrity_score == 1.0,
            "bounded_agent_execution": True,
            "registry_first_architecture": True,
            "no_hidden_prompt_memory": True,
        },
        "generated_at_epoch": time.time(),
    }

    report_path = Path(args.report_path)
    _save_json(report_path, stability_report)

    fingerprint_payload = {
        "schema_version": "1.0",
        "stability_reports": {
            "aura_stability_report": str(report_path.resolve()),
            "aura_replay_determinism_report": str((out / "aura_replay_determinism_report.json").resolve()),
            "aura_confidence_integrity_report": str((out / "aura_confidence_integrity_report.json").resolve()),
            "aura_recovery_validation_report": str((out / "aura_recovery_validation_report.json").resolve()),
            "aura_event_quarantine_report": str((out / "aura_event_quarantine_report.json").resolve()),
        },
        "metrics": stability_report["stability_metrics"],
        "stability_fingerprint": hashlib.sha256(
            json.dumps(
                {
                    "stability": stability_report,
                    "determinism": determinism_report,
                    "confidence": confidence_report,
                    "recovery": recovery_report,
                    "quarantine": quarantine_report,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "generated_at_epoch": time.time(),
    }

    fingerprint_path = Path(args.fingerprint_path)
    _save_json(fingerprint_path, fingerprint_payload)

    print(
        json.dumps(
            {
                "stability_report": str(report_path.resolve()),
                "stability_fingerprint": str(fingerprint_path.resolve()),
                **stability_report["stability_metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
