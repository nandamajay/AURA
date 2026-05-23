#!/usr/bin/env python3
"""RB3Gen2 deterministic governed playback stability harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_once(
    *,
    run_script: Path,
    bridge_root: Path,
    timeout_seconds: int,
    overwrite_policy: str,
    baseline_profile_id: str,
    baseline_profile_version: int,
    human_validation: str,
    execution_profile: str,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(run_script),
        "--bridge-root",
        str(bridge_root),
        "--live-run",
        "--timeout-seconds",
        str(timeout_seconds),
        "--overwrite-policy",
        overwrite_policy,
        "--human-audible-validation",
        human_validation,
        "--baseline-profile-id",
        baseline_profile_id,
        "--baseline-profile-version",
        str(baseline_profile_version),
        "--execution-profile",
        execution_profile,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": "playback_script_failed",
            "return_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "reason": "playback_script_non_json",
            "return_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    trace_path = Path(str(payload.get("trace", "")))
    if not trace_path.exists():
        return {
            "ok": False,
            "reason": "trace_missing",
            "return_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "payload": payload,
        }
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "payload": payload,
        "trace": trace,
        "stdout": stdout,
        "stderr": stderr,
    }


def _extract_command_sequence(trace: Mapping[str, Any]) -> list[str]:
    sequence: list[str] = []
    for phase in trace.get("phase_trace", []):
        if not isinstance(phase, dict):
            continue
        response = phase.get("response")
        if not isinstance(response, dict):
            continue
        for item in response.get("executor_command_trace", []):
            if not isinstance(item, dict):
                continue
            cmd = str(item.get("normalized_command", "")).strip()
            if cmd:
                sequence.append(cmd)
    return sequence


def _extract_evidence_sequence(trace: Mapping[str, Any]) -> list[str]:
    sequence: list[str] = []
    for phase in trace.get("phase_trace", []):
        if not isinstance(phase, dict):
            continue
        if phase.get("skipped", False):
            continue
        cmd = str(phase.get("snapshot_command", "")).strip()
        if cmd:
            sequence.append(cmd)
    return sequence


def _hash_list(values: list[str]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=False).encode("utf-8")).hexdigest()


def _mode(values: list[str]) -> str:
    if not values:
        return ""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts.items(), key=lambda x: x[1])[0]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="RB3 deterministic stability validation")
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--bridge-root",
        default="/local/mnt/workspace/AURA_V1/bridge",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
    )
    parser.add_argument(
        "--overwrite-policy",
        choices=("no_overwrite", "allow_overwrite"),
        default="allow_overwrite",
    )
    parser.add_argument(
        "--execution-profile",
        choices=("full_governed", "fast_locked_replay"),
        default="fast_locked_replay",
    )
    parser.add_argument(
        "--baseline-profile-id",
        default="audible_25s_speaker_v1",
    )
    parser.add_argument(
        "--baseline-profile-version",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--human-audible-validation",
        choices=("confirmed", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    args = parser.parse_args()

    run_script = REPO_ROOT / "scripts" / "rb3-runtime-procedural-playback.py"
    bridge_root = Path(args.bridge_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_records: list[dict[str, Any]] = []
    fail_closed_abort = False
    fail_closed_reason = ""

    for idx in range(1, args.runs + 1):
        result = _run_once(
            run_script=run_script,
            bridge_root=bridge_root,
            timeout_seconds=args.timeout_seconds,
            overwrite_policy=args.overwrite_policy,
            baseline_profile_id=args.baseline_profile_id,
            baseline_profile_version=args.baseline_profile_version,
            human_validation=args.human_audible_validation,
            execution_profile=args.execution_profile,
        )
        if not result.get("ok", False):
            fail_closed_abort = True
            fail_closed_reason = str(result.get("reason", "run_failed"))
            run_records.append({"run_index": idx, "result": result, "process_success": False})
            break

        trace = result["trace"]
        profile = trace.get("baseline_profile", {})
        timing = trace.get("playback_timing_verification", {})
        transport = profile.get("transport", {})
        command_sequence = _extract_command_sequence(trace)
        evidence_sequence = _extract_evidence_sequence(trace)
        record = {
            "run_index": idx,
            "run_id": str(trace.get("run_id", "")),
            "trace_path": str(result["payload"].get("trace", "")),
            "process_success": bool(trace.get("process_success", False)),
            "evidence_success": bool(trace.get("evidence_success", False)),
            "classification": str(trace.get("classification", "ADVISORY_ONLY")),
            "current_state": str(trace.get("current_state", trace.get("state_machine", {}).get("current_state", ""))),
            "wav_sha256": str(profile.get("wav_asset", {}).get("sha256", "")),
            "wav_duration_seconds": _safe_float(profile.get("wav_asset", {}).get("duration_seconds")),
            "pcm_alsa_device": str(profile.get("pcm", {}).get("alsa_device", "")),
            "pcm_signature": str(profile.get("pcm", {}).get("signature_sha256", "")),
            "route_fingerprint": str(profile.get("route", {}).get("route_fingerprint", "")),
            "playback_runtime_seconds": _safe_float(timing.get("playback_runtime_seconds")),
            "playback_duration_match": bool(timing.get("playback_duration_match", False)),
            "transport_timeout_count": int(transport.get("timeout_count", 0)),
            "transport_invalid_count": int(transport.get("invalid_count", 0)),
            "transport_disconnected_count": int(transport.get("disconnected_count", 0)),
            "evidence_quality": str(profile.get("evidence", {}).get("evidence_quality", "LOW")),
            "missing_evidence": list(profile.get("evidence", {}).get("missing_evidence", [])),
            "command_sequence": command_sequence,
            "command_sequence_hash": _hash_list(command_sequence),
            "evidence_sequence": evidence_sequence,
            "evidence_sequence_hash": _hash_list(evidence_sequence),
        }
        run_records.append(record)

        if not record["process_success"]:
            fail_closed_abort = True
            fail_closed_reason = "process_success_false"
            break

    completed = len([r for r in run_records if isinstance(r.get("run_index"), int)])
    successful = len([r for r in run_records if r.get("process_success") is True])
    evidence_success_count = len([r for r in run_records if r.get("evidence_success") is True])

    playback_runtimes = [_safe_float(r.get("playback_runtime_seconds")) for r in run_records if isinstance(r, dict)]
    wav_durations = [_safe_float(r.get("wav_duration_seconds")) for r in run_records if isinstance(r, dict)]
    pcm_signatures = [str(r.get("pcm_signature", "")) for r in run_records if isinstance(r, dict)]
    route_fingerprints = [str(r.get("route_fingerprint", "")) for r in run_records if isinstance(r, dict)]
    wav_sha_values = [str(r.get("wav_sha256", "")) for r in run_records if isinstance(r, dict)]
    command_hashes = [str(r.get("command_sequence_hash", "")) for r in run_records if isinstance(r, dict)]
    evidence_hashes = [str(r.get("evidence_sequence_hash", "")) for r in run_records if isinstance(r, dict)]

    transport_stable_runs = len(
        [
            r
            for r in run_records
            if isinstance(r, dict)
            and int(r.get("transport_timeout_count", 0)) == 0
            and int(r.get("transport_invalid_count", 0)) == 0
            and int(r.get("transport_disconnected_count", 0)) == 0
        ]
    )
    playback_stable_runs = len(
        [
            r
            for r in run_records
            if isinstance(r, dict)
            and bool(r.get("process_success", False))
            and bool(r.get("playback_duration_match", False))
        ]
    )

    total = max(1, completed)
    transport_confidence = round(transport_stable_runs / total, 3)
    playback_confidence = round(playback_stable_runs / total, 3)
    evidence_confidence = round(evidence_success_count / total, 3)

    route_mode = _mode(route_fingerprints)
    pcm_mode = _mode(pcm_signatures)
    route_stability = round(
        (route_fingerprints.count(route_mode) / total) if route_mode else 0.0,
        3,
    )
    pcm_stability = round(
        (pcm_signatures.count(pcm_mode) / total) if pcm_mode else 0.0,
        3,
    )
    topology_confidence = round(min(route_stability, pcm_stability), 3)
    runtime_confidence = round(
        (0.30 * transport_confidence)
        + (0.30 * playback_confidence)
        + (0.20 * evidence_confidence)
        + (0.20 * topology_confidence),
        3,
    )

    confidence_evolution: list[dict[str, Any]] = []
    for i in range(1, completed + 1):
        subset = run_records[:i]
        s_total = max(1, i)
        s_transport = len(
            [
                r
                for r in subset
                if int(r.get("transport_timeout_count", 0)) == 0
                and int(r.get("transport_invalid_count", 0)) == 0
                and int(r.get("transport_disconnected_count", 0)) == 0
            ]
        ) / s_total
        s_playback = len(
            [r for r in subset if bool(r.get("process_success", False)) and bool(r.get("playback_duration_match", False))]
        ) / s_total
        s_evidence = len([r for r in subset if bool(r.get("evidence_success", False))]) / s_total
        s_routes = [str(r.get("route_fingerprint", "")) for r in subset]
        s_pcm = [str(r.get("pcm_signature", "")) for r in subset]
        s_route_mode = _mode(s_routes)
        s_pcm_mode = _mode(s_pcm)
        s_topology = min(
            (s_routes.count(s_route_mode) / s_total) if s_route_mode else 0.0,
            (s_pcm.count(s_pcm_mode) / s_total) if s_pcm_mode else 0.0,
        )
        s_runtime = (0.30 * s_transport) + (0.30 * s_playback) + (0.20 * s_evidence) + (0.20 * s_topology)
        confidence_evolution.append(
            {
                "run_index": i,
                "transport_confidence": round(s_transport, 3),
                "playback_confidence": round(s_playback, 3),
                "evidence_confidence": round(s_evidence, 3),
                "topology_confidence": round(s_topology, 3),
                "runtime_confidence": round(s_runtime, 3),
            }
        )

    baseline_playback = playback_runtimes[0] if playback_runtimes else 0.0
    playback_drift = [
        {
            "run_index": int(r.get("run_index", 0)),
            "playback_runtime_seconds": _safe_float(r.get("playback_runtime_seconds")),
            "drift_seconds": round(_safe_float(r.get("playback_runtime_seconds")) - baseline_playback, 6),
        }
        for r in run_records
        if isinstance(r, dict)
    ]
    playback_drift_detected = any(abs(item["drift_seconds"]) > max(1.0, baseline_playback * 0.1) for item in playback_drift)
    playback_timing_stats = {
        "min_seconds": round(min(playback_runtimes), 6) if playback_runtimes else 0.0,
        "max_seconds": round(max(playback_runtimes), 6) if playback_runtimes else 0.0,
        "mean_seconds": round(statistics.mean(playback_runtimes), 6) if playback_runtimes else 0.0,
        "stdev_seconds": round(statistics.pstdev(playback_runtimes), 6) if len(playback_runtimes) > 1 else 0.0,
    }

    pcm_change_detected = len(set([v for v in pcm_signatures if v])) > 1
    route_instability_detected = len(set([v for v in route_fingerprints if v])) > 1
    degraded_evidence_runs = [
        int(r.get("run_index", 0))
        for r in run_records
        if isinstance(r, dict) and not bool(r.get("evidence_success", False))
    ]
    transport_instability_runs = [
        int(r.get("run_index", 0))
        for r in run_records
        if isinstance(r, dict)
        and (
            int(r.get("transport_timeout_count", 0)) > 0
            or int(r.get("transport_invalid_count", 0)) > 0
            or int(r.get("transport_disconnected_count", 0)) > 0
        )
    ]

    deterministic_runtime_profile = {
        "board": "RB3Gen2",
        "profile_id": args.baseline_profile_id,
        "profile_version": args.baseline_profile_version,
        "execution_profile": args.execution_profile,
        "target_runs": args.runs,
        "completed_runs": completed,
        "successful_runs": successful,
        "status": "STABLE" if (completed == args.runs and successful == args.runs and not fail_closed_abort) else "UNSTABLE",
        "fail_closed_abort": fail_closed_abort,
        "fail_closed_reason": fail_closed_reason,
        "wav_sha256": _mode(wav_sha_values),
        "wav_duration_seconds_mode": _safe_float(_mode([str(v) for v in wav_durations]), 0.0),
        "pcm_signature_mode": pcm_mode,
        "pcm_alsa_device_mode": _mode([str(r.get("pcm_alsa_device", "")) for r in run_records if isinstance(r, dict)]),
        "route_fingerprint_mode": route_mode,
        "playback_timing_stats": playback_timing_stats,
        "timing_windows": {
            "playback_runtime_min_max": [playback_timing_stats["min_seconds"], playback_timing_stats["max_seconds"]],
        },
        "evidence_quality_consistency": sorted(
            list(set([str(r.get("evidence_quality", "")) for r in run_records if isinstance(r, dict)]))
        ),
    }

    runtime_confidence_report = {
        "transport_confidence": transport_confidence,
        "playback_confidence": playback_confidence,
        "evidence_confidence": evidence_confidence,
        "runtime_confidence": runtime_confidence,
        "topology_confidence": topology_confidence,
        "confidence_evolution": confidence_evolution,
    }

    playback_drift_report = {
        "baseline_playback_runtime_seconds": baseline_playback,
        "playback_timing_stats": playback_timing_stats,
        "playback_drift": playback_drift,
        "playback_timing_drift_detected": playback_drift_detected,
        "pcm_mapping_changes_detected": pcm_change_detected,
        "route_instability_detected": route_instability_detected,
        "degraded_evidence_runs": degraded_evidence_runs,
        "transport_instability_runs": transport_instability_runs,
    }

    procedural_signature = {
        "execution_ordering_hashes": command_hashes,
        "execution_ordering_stable": len(set(command_hashes)) == 1 if command_hashes else False,
        "evidence_sequence_hashes": evidence_hashes,
        "evidence_sequence_stable": len(set(evidence_hashes)) == 1 if evidence_hashes else False,
        "execution_ordering_mode_hash": _mode(command_hashes),
        "evidence_sequence_mode_hash": _mode(evidence_hashes),
        "run_records": run_records,
    }

    stable_route_fingerprint = {
        "route_fingerprint": route_mode,
        "route_stability": route_stability,
        "pcm_signature": pcm_mode,
        "pcm_stability": pcm_stability,
        "topology_confidence": topology_confidence,
    }

    deterministic_runtime_profile_path = output_dir / "deterministic_runtime_profile.json"
    runtime_confidence_report_path = output_dir / "runtime_confidence_report.json"
    playback_drift_report_path = output_dir / "playback_drift_report.json"
    procedural_signature_path = output_dir / "procedural_signature.json"
    stable_route_fingerprint_path = output_dir / "stable_route_fingerprint.json"

    deterministic_runtime_profile_path.write_text(
        json.dumps(deterministic_runtime_profile, indent=2, sort_keys=True), encoding="utf-8"
    )
    runtime_confidence_report_path.write_text(
        json.dumps(runtime_confidence_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    playback_drift_report_path.write_text(
        json.dumps(playback_drift_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    procedural_signature_path.write_text(
        json.dumps(procedural_signature, indent=2, sort_keys=True), encoding="utf-8"
    )
    stable_route_fingerprint_path.write_text(
        json.dumps(stable_route_fingerprint, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "deterministic_runtime_profile": str(deterministic_runtime_profile_path.resolve()),
                "runtime_confidence_report": str(runtime_confidence_report_path.resolve()),
                "playback_drift_report": str(playback_drift_report_path.resolve()),
                "procedural_signature": str(procedural_signature_path.resolve()),
                "stable_route_fingerprint": str(stable_route_fingerprint_path.resolve()),
                "completed_runs": completed,
                "successful_runs": successful,
                "status": deterministic_runtime_profile["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if (completed == args.runs and successful == args.runs and not fail_closed_abort) else 5


if __name__ == "__main__":
    raise SystemExit(main())
