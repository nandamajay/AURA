"""Deterministic RB3Gen2 audible baseline registry and regression controls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_hash(payload: Mapping[str, Any]) -> str:
    return _sha256_text(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_runtime_regression_comparison(
    current_profile: Mapping[str, Any],
    baseline_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(baseline_profile, Mapping):
        payload = {
            "status": "NO_BASELINE",
            "regression_detected": False,
            "severity": "NONE",
            "deviations": [],
        }
        payload["regression_fingerprint"] = _stable_hash(payload)
        return payload

    deviations: list[dict[str, Any]] = []

    current_pcm = str(current_profile.get("pcm", {}).get("signature_sha256", ""))
    baseline_pcm = str(baseline_profile.get("pcm", {}).get("signature_sha256", ""))
    if current_pcm and baseline_pcm and current_pcm != baseline_pcm:
        deviations.append(
            {
                "code": "pcm_change",
                "severity": "HIGH",
                "details": "PCM signature changed from locked baseline.",
            }
        )

    current_route = str(current_profile.get("route", {}).get("route_fingerprint", ""))
    baseline_route = str(baseline_profile.get("route", {}).get("route_fingerprint", ""))
    if current_route and baseline_route and current_route != baseline_route:
        deviations.append(
            {
                "code": "route_change",
                "severity": "HIGH",
                "details": "Route topology fingerprint changed from baseline.",
            }
        )

    curr_total = _to_float(current_profile.get("runtime_timing", {}).get("total_runtime_seconds"))
    base_total = _to_float(baseline_profile.get("runtime_timing", {}).get("total_runtime_seconds"))
    if base_total > 0:
        drift = abs(curr_total - base_total)
        if drift > max(2.0, base_total * 0.2):
            deviations.append(
                {
                    "code": "runtime_latency_drift",
                    "severity": "MEDIUM",
                    "details": f"Total runtime drift {drift:.3f}s exceeds threshold.",
                }
            )

    curr_play = _to_float(current_profile.get("runtime_timing", {}).get("playback_runtime_seconds"))
    base_play = _to_float(baseline_profile.get("runtime_timing", {}).get("playback_runtime_seconds"))
    if base_play > 0:
        playback_drift = abs(curr_play - base_play)
        if playback_drift > max(1.0, base_play * 0.1):
            deviations.append(
                {
                    "code": "playback_timing_drift",
                    "severity": "MEDIUM",
                    "details": f"Playback runtime drift {playback_drift:.3f}s exceeds threshold.",
                }
            )

    curr_missing = {
        str(item)
        for item in current_profile.get("evidence", {}).get("missing_evidence", [])
        if str(item).strip()
    }
    base_missing = {
        str(item)
        for item in baseline_profile.get("evidence", {}).get("missing_evidence", [])
        if str(item).strip()
    }
    newly_missing = sorted(curr_missing - base_missing)
    if newly_missing:
        deviations.append(
            {
                "code": "missing_evidence",
                "severity": "MEDIUM",
                "details": f"New missing evidence detected: {', '.join(newly_missing)}",
            }
        )

    curr_timeout = int(current_profile.get("transport", {}).get("timeout_count", 0))
    base_timeout = int(baseline_profile.get("transport", {}).get("timeout_count", 0))
    if curr_timeout > base_timeout:
        deviations.append(
            {
                "code": "transport_degradation",
                "severity": "MEDIUM",
                "details": f"Timeout count increased from {base_timeout} to {curr_timeout}.",
            }
        )

    severity_order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    max_severity = "NONE"
    for item in deviations:
        sev = str(item.get("severity", "LOW")).upper()
        if severity_order.get(sev, 1) > severity_order.get(max_severity, 0):
            max_severity = sev

    payload = {
        "status": "COMPARED",
        "regression_detected": bool(deviations),
        "severity": max_severity,
        "deviations": deviations,
    }
    payload["regression_fingerprint"] = _stable_hash(
        {
            "status": payload["status"],
            "severity": payload["severity"],
            "deviations": payload["deviations"],
            "current_pcm": current_pcm,
            "current_route": current_route,
            "current_runtime": curr_total,
            "current_playback_runtime": curr_play,
        }
    )
    return payload


@dataclass(frozen=True)
class BaselineRecordResult:
    registry: dict[str, Any]
    profile: dict[str, Any]
    baseline_locked: bool


class RB3BaselineProfileRegistry:
    """Versioned baseline profile registry with confidence evolution."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _default_payload(self) -> dict[str, Any]:
        now = _utc_now_iso()
        return {
            "schema_version": "1.0",
            "board": "RB3Gen2",
            "created_at": now,
            "updated_at": now,
            "latest_profile_id": "audible_25s_speaker_v1",
            "profiles": {
                "audible_25s_speaker_v1": {
                    "profile_id": "audible_25s_speaker_v1",
                    "profile_version": 1,
                    "state": "CANDIDATE",
                    "confidence": {
                        "score": 0.0,
                        "successful_runs": 0,
                        "evidence_success_runs": 0,
                        "audible_confirmed_runs": 0,
                        "total_runs": 0,
                        "route_certainty": "LOW",
                    },
                    "baseline_profile": None,
                    "regression_history": [],
                    "lineage": [],
                    "runs": [],
                }
            },
        }

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._default_payload()
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, payload: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")

    def _ensure_profile(self, payload: dict[str, Any], profile_id: str, profile_version: int) -> dict[str, Any]:
        profiles = payload.setdefault("profiles", {})
        if profile_id not in profiles:
            profiles[profile_id] = {
                "profile_id": profile_id,
                "profile_version": int(profile_version),
                "state": "CANDIDATE",
                "confidence": {
                    "score": 0.0,
                    "successful_runs": 0,
                    "evidence_success_runs": 0,
                    "audible_confirmed_runs": 0,
                    "total_runs": 0,
                    "route_certainty": "LOW",
                },
                "baseline_profile": None,
                "regression_history": [],
                "lineage": [],
                "runs": [],
            }
        profile = profiles[profile_id]
        profile["profile_version"] = int(profile_version)
        return profile

    def record_run(
        self,
        *,
        profile_id: str,
        profile_version: int,
        run_id: str,
        runtime_profile: Mapping[str, Any],
        regression: Mapping[str, Any],
        evidence_lineage: Mapping[str, Any],
        process_success: bool,
        evidence_success: bool,
        audible_status: str,
    ) -> BaselineRecordResult:
        payload = self.load()
        profile = self._ensure_profile(payload, profile_id, profile_version)

        confidence = profile.setdefault("confidence", {})
        confidence["total_runs"] = int(confidence.get("total_runs", 0)) + 1
        if process_success:
            confidence["successful_runs"] = int(confidence.get("successful_runs", 0)) + 1
        if evidence_success:
            confidence["evidence_success_runs"] = int(confidence.get("evidence_success_runs", 0)) + 1
        if audible_status == "confirmed":
            confidence["audible_confirmed_runs"] = int(confidence.get("audible_confirmed_runs", 0)) + 1

        total_runs = max(1, int(confidence.get("total_runs", 1)))
        success_ratio = int(confidence.get("successful_runs", 0)) / total_runs
        evidence_ratio = int(confidence.get("evidence_success_runs", 0)) / total_runs
        audible_ratio = int(confidence.get("audible_confirmed_runs", 0)) / total_runs
        score = min(1.0, (0.45 * success_ratio) + (0.30 * evidence_ratio) + (0.25 * audible_ratio))
        confidence["score"] = round(score, 3)
        confidence["route_certainty"] = (
            "HIGH"
            if confidence["score"] >= 0.85
            else "MEDIUM"
            if confidence["score"] >= 0.60
            else "LOW"
        )

        regression_record = dict(regression)
        regression_record["run_id"] = run_id
        regression_record["recorded_at"] = _utc_now_iso()
        profile.setdefault("regression_history", []).append(regression_record)
        profile["regression_history"] = profile["regression_history"][-200:]

        lineage_record = dict(evidence_lineage)
        lineage_record["run_id"] = run_id
        lineage_record["recorded_at"] = _utc_now_iso()
        profile.setdefault("lineage", []).append(lineage_record)
        profile["lineage"] = profile["lineage"][-200:]

        run_summary = {
            "run_id": run_id,
            "recorded_at": _utc_now_iso(),
            "process_success": process_success,
            "evidence_success": evidence_success,
            "audible_status": audible_status,
            "final_classification": runtime_profile.get("final_classification", "ADVISORY_ONLY"),
            "regression_fingerprint": regression.get("regression_fingerprint", ""),
        }
        profile.setdefault("runs", []).append(run_summary)
        profile["runs"] = profile["runs"][-500:]

        lock_eligible = bool(process_success and audible_status == "confirmed")
        baseline_locked = False
        if profile.get("baseline_profile") is None and lock_eligible:
            profile["baseline_profile"] = dict(runtime_profile)
            profile["state"] = "LOCKED"
            profile["baseline_locked_at"] = _utc_now_iso()
            baseline_locked = True
        elif lock_eligible:
            baseline_profile = profile.get("baseline_profile")
            baseline_play = _to_float(
                (baseline_profile or {}).get("runtime_timing", {}).get("playback_runtime_seconds"),
                default=0.0,
            )
            current_play = _to_float(
                runtime_profile.get("runtime_timing", {}).get("playback_runtime_seconds"),
                default=0.0,
            )
            if baseline_play <= 0.0 < current_play:
                profile["baseline_profile"] = dict(runtime_profile)
                profile["baseline_repaired_at"] = _utc_now_iso()
            if not regression.get("regression_detected", False):
                profile["state"] = "LOCKED"

        payload["latest_profile_id"] = profile_id
        payload["updated_at"] = _utc_now_iso()
        self.save(payload)
        return BaselineRecordResult(
            registry=payload,
            profile=dict(profile),
            baseline_locked=baseline_locked,
        )


class RB3ProceduralMemoryLock:
    """Deterministic procedural replay lock with timing windows."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _default_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "board": "RB3Gen2",
            "lock_revision": 0,
            "lock_confidence": 0.0,
            "locked_profile_id": "",
            "successful_execution_sequence": [],
            "command_ordering": [],
            "cleanup_ordering": [],
            "evidence_collection_sequence": [],
            "timing_windows": {},
            "degradation_decisions": [],
            "history": [],
            "updated_at": _utc_now_iso(),
        }

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._default_payload()
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, payload: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")

    def record_run(
        self,
        *,
        run_id: str,
        profile_id: str,
        successful_sequence: list[str],
        command_ordering: list[str],
        cleanup_ordering: list[str],
        evidence_sequence: list[str],
        timing_windows: Mapping[str, float],
        degradation_decisions: list[str],
        process_success: bool,
        evidence_success: bool,
        audible_status: str,
    ) -> dict[str, Any]:
        payload = self.load()

        for key, value in timing_windows.items():
            bucket = payload.setdefault("timing_windows", {}).setdefault(
                key,
                {"min_seconds": None, "max_seconds": None, "last_seconds": 0.0},
            )
            v = _to_float(value)
            bucket["last_seconds"] = v
            bucket["min_seconds"] = v if bucket["min_seconds"] is None else min(v, _to_float(bucket["min_seconds"]))
            bucket["max_seconds"] = v if bucket["max_seconds"] is None else max(v, _to_float(bucket["max_seconds"]))

        lock_eligible = bool(process_success and audible_status == "confirmed")
        if lock_eligible:
            payload["lock_revision"] = int(payload.get("lock_revision", 0)) + 1
            payload["locked_profile_id"] = profile_id
            payload["successful_execution_sequence"] = successful_sequence
            payload["command_ordering"] = command_ordering
            payload["cleanup_ordering"] = cleanup_ordering
            payload["evidence_collection_sequence"] = evidence_sequence
            payload["degradation_decisions"] = degradation_decisions
            payload["lock_confidence"] = round(min(1.0, _to_float(payload.get("lock_confidence", 0.0)) + 0.1), 3)

        payload.setdefault("history", []).append(
            {
                "run_id": run_id,
                "recorded_at": _utc_now_iso(),
                "profile_id": profile_id,
                "process_success": process_success,
                "evidence_success": evidence_success,
                "audible_status": audible_status,
            }
        )
        payload["history"] = payload["history"][-500:]
        payload["updated_at"] = _utc_now_iso()
        self.save(payload)
        return payload
