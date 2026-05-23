"""AURA Cognitive Persistence Framework for RB3Gen2 governed playback.

This module moves cognition from transient prompt context into persistent
machine-readable state that can survive session loss, runtime restarts, and
operator/provider changes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = _load_json(path)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_list(values: Any) -> list[Any]:
    if isinstance(values, list):
        return values
    return []


def _coerce_dict(values: Any) -> dict[str, Any]:
    if isinstance(values, dict):
        return values
    return {}


def _dedupe_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _extract_overlay_knowledge(
    *,
    baseline_registry: Mapping[str, Any],
    route_memory: Mapping[str, Any],
) -> dict[str, Any]:
    overlays: dict[str, dict[str, Any]] = {}

    for profile in _coerce_dict(baseline_registry.get("profiles")).values():
        prof = _coerce_dict(profile)
        base = _coerce_dict(prof.get("baseline_profile"))
        overlay = str(base.get("overlay", "")).strip()
        if not overlay:
            continue
        entry = overlays.setdefault(
            overlay,
            {
                "overlay": overlay,
                "baseline_profile_ids": [],
                "route_fingerprints": [],
                "pcm_signatures": [],
            },
        )
        entry["baseline_profile_ids"] = _dedupe_strings(entry["baseline_profile_ids"] + [str(prof.get("profile_id", ""))])
        entry["route_fingerprints"] = _dedupe_strings(
            entry["route_fingerprints"] + [str(_coerce_dict(base.get("route")).get("route_fingerprint", ""))]
        )
        entry["pcm_signatures"] = _dedupe_strings(
            entry["pcm_signatures"] + [str(_coerce_dict(base.get("pcm")).get("signature_sha256", ""))]
        )

    for route in _coerce_list(route_memory.get("overlay_specific_procedural_flows")):
        item = _coerce_dict(route)
        overlay = str(item.get("overlay", "")).strip()
        if not overlay:
            continue
        entry = overlays.setdefault(
            overlay,
            {
                "overlay": overlay,
                "baseline_profile_ids": [],
                "route_fingerprints": [],
                "pcm_signatures": [],
            },
        )
        alignment = _coerce_dict(item.get("deterministic_alignment"))
        if alignment:
            entry.setdefault("deterministic_alignment_samples", []).append(alignment)

    return {
        "count": len(overlays),
        "overlays": sorted(overlays.values(), key=lambda x: str(x.get("overlay", ""))),
    }


def _extract_target_knowledge(
    *,
    runtime_report: Mapping[str, Any],
    baseline_registry: Mapping[str, Any],
) -> dict[str, Any]:
    fingerprint = _coerce_dict(runtime_report.get("fingerprint"))
    audio_discovery = _coerce_dict(fingerprint.get("audio_discovery"))
    environment = _coerce_dict(fingerprint.get("environment"))
    capabilities = _coerce_dict(fingerprint.get("capabilities"))
    cards = _coerce_list(audio_discovery.get("alsa_topology_cards"))

    known_pcm_signatures: list[str] = []
    known_route_fingerprints: list[str] = []
    for profile in _coerce_dict(baseline_registry.get("profiles")).values():
        base = _coerce_dict(_coerce_dict(profile).get("baseline_profile"))
        known_pcm_signatures.append(str(_coerce_dict(base.get("pcm")).get("signature_sha256", "")))
        known_route_fingerprints.append(str(_coerce_dict(base.get("route")).get("route_fingerprint", "")))

    return {
        "board": "RB3Gen2",
        "environment": environment,
        "capabilities": capabilities,
        "cards": cards,
        "known_pcm_signatures": _dedupe_strings(known_pcm_signatures),
        "known_route_fingerprints": _dedupe_strings(known_route_fingerprints),
    }


def _build_cognition_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    nodes.append({"id": "board:RB3Gen2", "kind": "board", "label": "RB3Gen2"})
    nodes.append({"id": "phase_engine", "kind": "phase_engine", "label": str(_coerce_dict(payload.get("phase_engine")).get("current_phase", "UNKNOWN"))})
    nodes.append({"id": "governance_engine", "kind": "governance_engine", "label": str(_coerce_dict(payload.get("governance_engine")).get("execution_approval_mode", "UNKNOWN"))})
    nodes.append({"id": "runtime_cognition", "kind": "runtime_cognition", "label": "runtime_cognition"})
    nodes.append({"id": "topology_cognition", "kind": "topology_cognition", "label": "topology_cognition"})
    nodes.append({"id": "baseline_registry", "kind": "baseline_registry", "label": "baseline_registry"})
    nodes.append({"id": "procedural_memory", "kind": "procedural_memory", "label": "procedural_memory"})
    nodes.append({"id": "regression_lineage", "kind": "regression_lineage", "label": "regression_lineage"})
    nodes.append({"id": "target_knowledge", "kind": "target_knowledge", "label": "target_knowledge"})
    nodes.append({"id": "overlay_knowledge", "kind": "overlay_knowledge", "label": "overlay_knowledge"})

    edges.extend(
        [
            {"from": "board:RB3Gen2", "to": "phase_engine", "relation": "governed_by"},
            {"from": "board:RB3Gen2", "to": "governance_engine", "relation": "enforced_by"},
            {"from": "board:RB3Gen2", "to": "runtime_cognition", "relation": "observed_by"},
            {"from": "runtime_cognition", "to": "topology_cognition", "relation": "correlates_with"},
            {"from": "runtime_cognition", "to": "baseline_registry", "relation": "compares_against"},
            {"from": "runtime_cognition", "to": "procedural_memory", "relation": "persists_into"},
            {"from": "topology_cognition", "to": "overlay_knowledge", "relation": "updates"},
            {"from": "runtime_cognition", "to": "target_knowledge", "relation": "updates"},
            {"from": "baseline_registry", "to": "regression_lineage", "relation": "feeds"},
        ]
    )

    return {"nodes": nodes, "edges": edges}


def _default_phase_state() -> dict[str, Any]:
    return {
        "current_phase": "RB3_DETERMINISTIC_TOPOLOGY_INTELLIGENCE",
        "enabled_capabilities": [
            "rb3_playback_planning",
            "rb3_playback_execution",
            "rb3_runtime_cognition",
            "rb3_topology_cognition",
            "rb3_regression_tracking",
            "artifact_persistence",
            "cognition_replay",
        ],
        "blocked_capabilities": [
            "capture_workflows",
            "new_targets",
            "autonomous_patching",
            "autonomous_topology_rewriting",
            "autonomous_upstream_generation",
        ],
        "allowed_execution_scope": [
            "board:RB3Gen2",
            "workflow:playback",
            "transport:adb_shell",
        ],
        "governance_restrictions": [
            "fail_closed",
            "write_requires_approval",
            "topology_mutation_blocked",
            "no_autonomous_patching",
        ],
        "updated_at": _utc_now_iso(),
    }


def _default_governance_state() -> dict[str, Any]:
    return {
        "fail_closed_posture": True,
        "write_policy": "governed_write_approved_only",
        "execution_approval_mode": "linux_authoritative_windows_execute_only",
        "transport_restrictions": {
            "allowed_modes": ["adb_shell"],
            "blocked_modes": ["serial_raw", "ssh_unapproved"],
        },
        "patching_restrictions": {
            "autonomous_patching_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
        "topology_mutation_restrictions": {
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_mixer_mutation_allowed": False,
        },
        "updated_at": _utc_now_iso(),
    }


def _default_registry() -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "schema_version": "1.0",
        "board": "RB3Gen2",
        "created_at": now,
        "updated_at": now,
        "runtime_cognition": {},
        "topology_cognition": {},
        "governance_state": _default_governance_state(),
        "phase_state": _default_phase_state(),
        "procedural_memory": {},
        "baseline_registry": {},
        "confidence_evolution": [],
        "regression_lineage": [],
        "target_knowledge": {},
        "overlay_knowledge": {},
        "execution_policies": {
            "phase_enforcement_enabled": True,
            "governance_enforcement_enabled": True,
            "policy_source": "persistent_registry",
        },
        "cognition_lineage": [],
        "cognition_graph": {"nodes": [], "edges": []},
    }


@dataclass(frozen=True)
class CognitionBootResult:
    registry: dict[str, Any]
    phase_state: dict[str, Any]
    governance_state: dict[str, Any]
    boot_summary: dict[str, Any]


class AURAPhaseEngine:
    """Persistent phase enforcement independent of prompt context."""

    def __init__(self, phase_state: Mapping[str, Any] | None = None):
        state = _default_phase_state()
        state.update(_coerce_dict(phase_state))
        state["enabled_capabilities"] = _dedupe_strings(_coerce_list(state.get("enabled_capabilities")))
        state["blocked_capabilities"] = _dedupe_strings(_coerce_list(state.get("blocked_capabilities")))
        state["allowed_execution_scope"] = _dedupe_strings(_coerce_list(state.get("allowed_execution_scope")))
        state["governance_restrictions"] = _dedupe_strings(_coerce_list(state.get("governance_restrictions")))
        self._state = state

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def assert_capability(self, capability: str) -> None:
        cap = str(capability).strip()
        if not cap:
            raise PermissionError("phase_capability_invalid")
        if cap in set(self._state.get("blocked_capabilities", [])):
            raise PermissionError(f"phase_blocked_capability:{cap}")
        enabled = set(self._state.get("enabled_capabilities", []))
        if cap not in enabled:
            raise PermissionError(f"phase_capability_not_enabled:{cap}")

    def assert_execution_scope(self, scope_token: str) -> None:
        token = str(scope_token).strip()
        if not token:
            raise PermissionError("phase_scope_invalid")
        allowed = set(self._state.get("allowed_execution_scope", []))
        if token not in allowed:
            raise PermissionError(f"phase_scope_blocked:{token}")


class AURAGovernanceEngine:
    """Persistent governance enforcement that survives runtime/session changes."""

    def __init__(self, governance_state: Mapping[str, Any] | None = None):
        state = _default_governance_state()
        state.update(_coerce_dict(governance_state))
        self._state = state

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def assert_transport_allowed(self, transport_mode: str) -> None:
        mode = str(transport_mode).strip()
        restrictions = _coerce_dict(self._state.get("transport_restrictions"))
        allowed = set(_dedupe_strings(_coerce_list(restrictions.get("allowed_modes"))))
        blocked = set(_dedupe_strings(_coerce_list(restrictions.get("blocked_modes"))))
        if mode in blocked:
            raise PermissionError(f"governance_transport_blocked:{mode}")
        if allowed and mode not in allowed:
            raise PermissionError(f"governance_transport_not_allowed:{mode}")

    def assert_write_allowed(self, *, execution_mode: str, allow_write_ops: bool) -> None:
        write_policy = str(self._state.get("write_policy", ""))
        mode = str(execution_mode).strip()
        if not allow_write_ops:
            return
        if write_policy == "governed_write_approved_only" and mode != "governed_write_approved":
            raise PermissionError("governance_write_policy_violation")

    def assert_action(
        self,
        *,
        action: str,
        execution_mode: str,
        allow_write_ops: bool,
        transport_mode: str,
    ) -> None:
        fail_closed = bool(self._state.get("fail_closed_posture", True))
        if not fail_closed:
            return
        self.assert_transport_allowed(transport_mode)
        self.assert_write_allowed(execution_mode=execution_mode, allow_write_ops=allow_write_ops)

        action_text = str(action).strip().lower()
        patching = _coerce_dict(self._state.get("patching_restrictions"))
        topology = _coerce_dict(self._state.get("topology_mutation_restrictions"))
        if "patch" in action_text and not bool(patching.get("autonomous_patching_allowed", False)):
            raise PermissionError("governance_autonomous_patching_blocked")
        if "upstream" in action_text and not bool(patching.get("autonomous_upstream_generation_allowed", False)):
            raise PermissionError("governance_upstream_generation_blocked")
        if "topology_mutation" in action_text and not bool(
            topology.get("autonomous_topology_rewrite_allowed", False)
        ):
            raise PermissionError("governance_topology_mutation_blocked")


class AURACognitionRegistry:
    """Persistent machine-readable cognition source of truth."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return _default_registry()
        payload = _load_json_if_exists(self._path)
        if not payload:
            return _default_registry()
        merged = _default_registry()
        merged.update(payload)
        return merged

    def save(self, payload: Mapping[str, Any]) -> None:
        _save_json(self._path, payload)

    def record_runtime_update(
        self,
        *,
        run_id: str,
        phase_state: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        runtime_cognition: Mapping[str, Any],
        topology_cognition: Mapping[str, Any],
        procedural_memory: Mapping[str, Any],
        baseline_registry: Mapping[str, Any],
        regression: Mapping[str, Any],
        target_knowledge: Mapping[str, Any],
        overlay_knowledge: Mapping[str, Any],
        lineage_entry: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = self.load()
        payload["phase_state"] = dict(phase_state)
        payload["governance_state"] = dict(governance_state)
        payload["runtime_cognition"] = dict(runtime_cognition)
        payload["topology_cognition"] = dict(topology_cognition)
        payload["procedural_memory"] = dict(procedural_memory)
        payload["baseline_registry"] = dict(baseline_registry)
        payload["target_knowledge"] = dict(target_knowledge)
        payload["overlay_knowledge"] = dict(overlay_knowledge)

        baseline_confidence = _coerce_dict(baseline_registry.get("confidence"))
        if not baseline_confidence:
            baseline_confidence = _coerce_dict(_coerce_dict(baseline_registry.get("profile")).get("confidence"))
        if not baseline_confidence:
            registry_profiles = _coerce_dict(baseline_registry.get("profiles"))
            latest_id = str(baseline_registry.get("latest_profile_id", "")).strip()
            latest = _coerce_dict(registry_profiles.get(latest_id))
            if not latest and registry_profiles:
                latest = _coerce_dict(next(iter(registry_profiles.values())))
            baseline_confidence = _coerce_dict(latest.get("confidence"))

        confidence = {
            "run_id": run_id,
            "recorded_at": _utc_now_iso(),
            "runtime_confidence": float(_coerce_dict(runtime_cognition.get("confidence")).get("runtime_confidence", 0.0)),
            "topology_confidence": float(topology_cognition.get("topology_confidence", 0.0)),
            "route_certainty": str(baseline_confidence.get("route_certainty", "LOW")),
        }
        payload.setdefault("confidence_evolution", []).append(confidence)
        payload["confidence_evolution"] = _coerce_list(payload["confidence_evolution"])[-500:]

        regression_record = dict(regression)
        regression_record["run_id"] = run_id
        regression_record["recorded_at"] = _utc_now_iso()
        payload.setdefault("regression_lineage", []).append(regression_record)
        payload["regression_lineage"] = _coerce_list(payload["regression_lineage"])[-500:]

        lineage = dict(lineage_entry)
        lineage["run_id"] = run_id
        lineage["recorded_at"] = _utc_now_iso()
        payload.setdefault("cognition_lineage", []).append(lineage)
        payload["cognition_lineage"] = _coerce_list(payload["cognition_lineage"])[-1000:]

        payload["cognition_graph"] = _build_cognition_graph(payload)
        payload["updated_at"] = _utc_now_iso()
        self.save(payload)
        return payload


class AURAArtifactIndexEngine:
    """Searchable artifact index for cognition, runtime, and governance artifacts."""

    def __init__(self, index_path: str | Path, artifact_root: str | Path):
        self._index_path = Path(index_path)
        self._root = Path(artifact_root)

    def _default_index(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "updated_at": _utc_now_iso(),
            "artifact_root": str(self._root.resolve()),
            "artifacts": [],
        }

    def load(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return self._default_index()
        payload = _load_json_if_exists(self._index_path)
        if not payload:
            return self._default_index()
        merged = self._default_index()
        merged.update(payload)
        return merged

    def save(self, payload: Mapping[str, Any]) -> None:
        _save_json(self._index_path, payload)

    def _category_for_file(self, name: str) -> str:
        if name in {"rb3_runtime_procedural_execution_trace.json", "rb3_runtime_validation_correlation_live.json"}:
            return "runtime_trace"
        if name in {"topology_graph.json", "runtime_route_graph.json", "overlay_mutation_graph.json", "pcm_backend_correlation.json"}:
            return "topology_graph"
        if name in {"rb3gen2_regression_fingerprint.json", "playback_drift_report.json"}:
            return "regression_report"
        if name.startswith("rb3gen2_baseline_profile_"):
            return "baseline_profile"
        if name in {"procedural_signature.json", "rb3gen2_procedural_memory_lock_snapshot.json", "procedural_route_memory.json"}:
            return "procedural_signature"
        if name in {"aura_governance_state.json", "aura_phase_state.json", "aura_cognition_registry.json"}:
            return "governance_decision"
        if name in {"rb3gen2_baseline_evidence_lineage.json"} or name.startswith("bridge_lineage_"):
            return "validation_lineage"
        return "misc"

    def refresh(self) -> dict[str, Any]:
        payload = self._default_index()
        artifacts: list[dict[str, Any]] = []
        if not self._root.exists():
            self.save(payload)
            return payload

        for path in sorted(self._root.glob("*")):
            if not path.is_file():
                continue
            category = self._category_for_file(path.name)
            entry = {
                "artifact_id": hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest(),
                "category": category,
                "path_abs": str(path.resolve()),
                "relative_path": str(path.resolve().relative_to(self._root.resolve())),
                "file_name": path.name,
                "size_bytes": int(path.stat().st_size),
                "modified_at_epoch": float(path.stat().st_mtime),
                "sha256": _sha256_file(path),
                "tags": [category, "rb3gen2", "cognitive_persistence"],
            }
            artifacts.append(entry)

        payload["updated_at"] = _utc_now_iso()
        payload["artifacts"] = artifacts
        self.save(payload)
        return payload

    def search(self, *, category: str = "", text: str = "") -> list[dict[str, Any]]:
        payload = self.load()
        category_filter = str(category).strip()
        text_filter = str(text).strip().lower()
        out: list[dict[str, Any]] = []
        for item in _coerce_list(payload.get("artifacts")):
            artifact = _coerce_dict(item)
            if category_filter and str(artifact.get("category", "")) != category_filter:
                continue
            hay = f"{artifact.get('file_name', '')} {artifact.get('path_abs', '')} {artifact.get('category', '')}".lower()
            if text_filter and text_filter not in hay:
                continue
            out.append(artifact)
        return out


class AURACognitionPortability:
    """Portable cognition export/import across sessions, terminals, and machines."""

    def export_snapshot(
        self,
        *,
        output_path: str | Path,
        registry: Mapping[str, Any],
        phase_state: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        artifact_index: Mapping[str, Any],
        artifact_root: str | Path,
    ) -> dict[str, Any]:
        root = Path(artifact_root)
        critical_files = [
            "deterministic_runtime_profile.json",
            "runtime_confidence_report.json",
            "playback_drift_report.json",
            "procedural_signature.json",
            "stable_route_fingerprint.json",
            "topology_graph.json",
            "runtime_route_graph.json",
            "overlay_mutation_graph.json",
            "pcm_backend_correlation.json",
            "playback_route_trace.json",
            "topology_confidence_report.json",
            "procedural_route_memory.json",
            "rb3gen2_audible_baseline_registry.json",
            "rb3gen2_procedural_memory_lock_snapshot.json",
            "rb3gen2_procedural_memory.json",
        ]

        artifacts_payload: list[dict[str, Any]] = []
        for name in critical_files:
            path = root / name
            if not path.exists() or not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            artifacts_payload.append(
                {
                    "relative_path": name,
                    "sha256": _sha256_file(path),
                    "content": content,
                }
            )

        snapshot = {
            "schema_version": "1.0",
            "exported_at": _utc_now_iso(),
            "board": "RB3Gen2",
            "registry": dict(registry),
            "phase_state": dict(phase_state),
            "governance_state": dict(governance_state),
            "artifact_index": dict(artifact_index),
            "artifacts": artifacts_payload,
        }
        _save_json(Path(output_path), snapshot)
        return snapshot

    def import_snapshot(
        self,
        *,
        snapshot_path: str | Path,
        target_registry_path: str | Path,
        target_phase_state_path: str | Path,
        target_governance_state_path: str | Path,
        target_artifact_index_path: str | Path,
        target_artifact_root: str | Path,
    ) -> dict[str, Any]:
        snapshot = _load_json(Path(snapshot_path))
        _save_json(Path(target_registry_path), _coerce_dict(snapshot.get("registry")))
        _save_json(Path(target_phase_state_path), _coerce_dict(snapshot.get("phase_state")))
        _save_json(Path(target_governance_state_path), _coerce_dict(snapshot.get("governance_state")))
        _save_json(Path(target_artifact_index_path), _coerce_dict(snapshot.get("artifact_index")))

        root = Path(target_artifact_root)
        root.mkdir(parents=True, exist_ok=True)
        restored: list[str] = []
        for item in _coerce_list(snapshot.get("artifacts")):
            artifact = _coerce_dict(item)
            rel = str(artifact.get("relative_path", "")).strip()
            if not rel:
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(str(artifact.get("content", "")), encoding="utf-8")
            restored.append(str(dst.resolve()))

        return {
            "status": "IMPORTED",
            "restored_artifact_count": len(restored),
            "restored_artifacts": restored,
        }


class AURACognitionReplayEngine:
    """Build deterministic replay plans from persisted cognition state only."""

    def __init__(
        self,
        *,
        baseline_registry_path: str | Path,
        procedural_lock_path: str | Path,
        procedural_route_memory_path: str | Path,
        phase_state_path: str | Path,
        governance_state_path: str | Path,
    ):
        self._baseline_registry_path = Path(baseline_registry_path)
        self._procedural_lock_path = Path(procedural_lock_path)
        self._procedural_route_memory_path = Path(procedural_route_memory_path)
        self._phase_state_path = Path(phase_state_path)
        self._governance_state_path = Path(governance_state_path)

    def build_known_good_replay(self, profile_id: str = "audible_25s_speaker_v1") -> dict[str, Any]:
        baseline_registry = _load_json_if_exists(self._baseline_registry_path)
        profiles = _coerce_dict(baseline_registry.get("profiles"))
        profile = _coerce_dict(profiles.get(profile_id))
        baseline = _coerce_dict(profile.get("baseline_profile"))
        if not baseline:
            raise ValueError("replay_no_locked_baseline")

        lock = _load_json_if_exists(self._procedural_lock_path)
        route_memory = _load_json_if_exists(self._procedural_route_memory_path)
        phase_state = _load_json_if_exists(self._phase_state_path) or _default_phase_state()
        governance_state = _load_json_if_exists(self._governance_state_path) or _default_governance_state()

        replay_plan = {
            "board": "RB3Gen2",
            "profile_id": profile_id,
            "overlay": str(baseline.get("overlay", "UNRESOLVED")),
            "wav_asset": _coerce_dict(baseline.get("wav_asset")),
            "pcm": _coerce_dict(baseline.get("pcm")),
            "route": _coerce_dict(baseline.get("route")),
            "execution_sequence": _coerce_list(lock.get("successful_execution_sequence")),
            "command_ordering": _coerce_list(lock.get("command_ordering")),
            "evidence_collection_sequence": _coerce_list(lock.get("evidence_collection_sequence")),
            "timing_windows": _coerce_dict(lock.get("timing_windows")),
            "procedural_route_memory": route_memory,
            "phase_state": phase_state,
            "governance_state": governance_state,
            "replay_ready": bool(lock.get("successful_execution_sequence")) and bool(baseline),
            "governance_posture": "fail_closed",
        }
        return replay_plan


class AURACognitionBootLoader:
    """Reconstruct cognition state from artifacts at startup."""

    def __init__(
        self,
        *,
        registry_path: str | Path,
        phase_state_path: str | Path,
        governance_state_path: str | Path,
        output_dir: str | Path,
        runtime_report_path: str | Path,
        baseline_registry_path: str | Path,
        procedural_memory_path: str | Path,
        procedural_lock_path: str | Path,
        procedural_route_memory_path: str | Path,
    ):
        self._registry_path = Path(registry_path)
        self._phase_state_path = Path(phase_state_path)
        self._governance_state_path = Path(governance_state_path)
        self._output_dir = Path(output_dir)
        self._runtime_report_path = Path(runtime_report_path)
        self._baseline_registry_path = Path(baseline_registry_path)
        self._procedural_memory_path = Path(procedural_memory_path)
        self._procedural_lock_path = Path(procedural_lock_path)
        self._procedural_route_memory_path = Path(procedural_route_memory_path)

    def boot(self) -> CognitionBootResult:
        registry_store = AURACognitionRegistry(self._registry_path)
        registry = registry_store.load()

        phase_state = _load_json_if_exists(self._phase_state_path)
        if not phase_state:
            phase_state = _coerce_dict(registry.get("phase_state")) or _default_phase_state()
        governance_state = _load_json_if_exists(self._governance_state_path)
        if not governance_state:
            governance_state = _coerce_dict(registry.get("governance_state")) or _default_governance_state()

        runtime_report = _load_json_if_exists(self._runtime_report_path)
        baseline_registry = _load_json_if_exists(self._baseline_registry_path)
        procedural_memory = _load_json_if_exists(self._procedural_memory_path)
        procedural_lock = _load_json_if_exists(self._procedural_lock_path)
        procedural_route_memory = _load_json_if_exists(self._procedural_route_memory_path)
        runtime_confidence = _load_json_if_exists(self._output_dir / "runtime_confidence_report.json")
        topology_confidence = _load_json_if_exists(self._output_dir / "topology_confidence_report.json")
        regression = _load_json_if_exists(self._output_dir / "rb3gen2_regression_fingerprint.json")
        trace = _load_json_if_exists(self._output_dir / "rb3_runtime_procedural_execution_trace.json")

        overlay_knowledge = _extract_overlay_knowledge(
            baseline_registry=baseline_registry,
            route_memory=procedural_route_memory,
        )
        target_knowledge = _extract_target_knowledge(
            runtime_report=runtime_report,
            baseline_registry=baseline_registry,
        )

        registry["phase_state"] = phase_state
        registry["governance_state"] = governance_state
        registry["runtime_cognition"] = {
            "confidence": runtime_confidence,
            "last_trace_summary": {
                "run_id": str(trace.get("run_id", "")),
                "classification": str(trace.get("classification", "ADVISORY_ONLY")),
                "process_success": bool(trace.get("process_success", False)),
                "evidence_success": bool(trace.get("evidence_success", False)),
            },
            "procedural_lock": procedural_lock,
        }
        registry["topology_cognition"] = {
            "confidence": topology_confidence,
            "procedural_route_memory": procedural_route_memory,
        }
        registry["procedural_memory"] = procedural_memory
        registry["baseline_registry"] = baseline_registry
        registry["target_knowledge"] = target_knowledge
        registry["overlay_knowledge"] = overlay_knowledge
        registry.setdefault("regression_lineage", [])
        if regression:
            registry["regression_lineage"] = (_coerce_list(registry.get("regression_lineage")) + [regression])[-500:]
        registry["execution_policies"] = {
            "phase_enforcement_enabled": True,
            "governance_enforcement_enabled": True,
            "policy_source": "persistent_registry",
        }
        registry["cognition_graph"] = _build_cognition_graph(registry)
        registry["updated_at"] = _utc_now_iso()

        _save_json(self._phase_state_path, phase_state)
        _save_json(self._governance_state_path, governance_state)
        registry_store.save(registry)

        boot_summary = {
            "booted_at": _utc_now_iso(),
            "loaded_governance_state": bool(governance_state),
            "loaded_phase_state": bool(phase_state),
            "loaded_procedural_memory": bool(procedural_memory),
            "loaded_baseline_registry": bool(baseline_registry),
            "loaded_topology_memory": bool(procedural_route_memory),
            "loaded_regression_history": bool(registry.get("regression_lineage")),
            "cognition_graph_nodes": len(_coerce_list(_coerce_dict(registry.get("cognition_graph")).get("nodes"))),
            "execution_policies_restored": True,
        }
        return CognitionBootResult(
            registry=registry,
            phase_state=phase_state,
            governance_state=governance_state,
            boot_summary=boot_summary,
        )


def copy_portable_snapshot(
    *,
    source_snapshot_path: str | Path,
    destination_snapshot_path: str | Path,
) -> str:
    src = Path(source_snapshot_path)
    dst = Path(destination_snapshot_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst.resolve())
