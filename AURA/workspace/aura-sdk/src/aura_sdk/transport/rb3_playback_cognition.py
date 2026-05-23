"""RB3Gen2 speaker playback cognition with governed fail-closed planning.

This module is Linux-governance-side only. It plans and reasons using evidence;
it does not perform autonomous destructive runtime mutation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_REGISTRY = Path(__file__).with_name("rb3_wav_asset_registry.json")
RB3_AUDIOREACH_OVERLAY = "qcs6490-audioreach.dtsi"
RB3_OPERATOR_PROVEN_SPEAKER_SEQUENCE: list[tuple[str, str]] = [
    ("SpkrLeft PA Volume", "20"),
    ("WSA RX0 MUX", "AIF1_PB"),
    ("WSA_RX0 INP0", "RX0"),
    ("WSA_COMP1 Switch", "1"),
    ("SpkrLeft WSA MODE", "0"),
    ("SpkrLeft COMP Switch", "1"),
    ("SpkrLeft BOOST Switch", "1"),
    ("SpkrLeft DAC Switch", "1"),
    ("SpkrLeft VISENSE Switch", "0"),
    ("WSA_RX0 Digital Volume", "85"),
    ("SpkrRight WSA MODE", "0"),
    ("SpkrRight PA Volume", "20"),
    ("WSA RX1 MUX", "AIF1_PB"),
    ("WSA_RX1 INP0", "RX1"),
    ("WSA_COMP2 Switch", "1"),
    ("SpkrRight COMP Switch", "1"),
    ("SpkrRight BOOST Switch", "1"),
    ("SpkrRight DAC Switch", "1"),
    ("SpkrRight VISENSE Switch", "0"),
    ("WSA_RX1 Digital Volume", "85"),
    ("WSA_CODEC_DMA_RX_0 Audio Mixer MultiMedia1", "1"),
]


@dataclass(frozen=True)
class RB3PlaybackPlanResult:
    plan: dict[str, Any]


class RB3ProceduralMemory:
    """Persistent board-specific procedural memory with deterministic updates."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {
                "board": "RB3Gen2",
                "successful_wav_assets": [],
                "successful_playback_procedures": [],
                "board_specific_quirks": [],
                "unsupported_formats": [],
                "route_specific_constraints": [],
                "recovery_patterns": [],
                "runtime_signatures": [],
                "failure_signatures": [],
                "history": [],
            }
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, payload: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")

    def record_result(
        self,
        *,
        run_id: str,
        success: bool,
        asset_id: str,
        overlay: str,
        mixer_sequence: list[str],
        quirks: list[str],
        unsupported_format: str | None,
        route_constraints: list[str],
        recovery_patterns: list[str],
        runtime_signature: Mapping[str, Any] | None = None,
        failure_signature: str | None = None,
    ) -> dict[str, Any]:
        payload = self.load()

        if success and asset_id and asset_id not in payload["successful_wav_assets"]:
            payload["successful_wav_assets"].append(asset_id)

        if success:
            signature = {
                "overlay": overlay,
                "mixer_sequence": mixer_sequence,
            }
            if signature not in payload["successful_playback_procedures"]:
                payload["successful_playback_procedures"].append(signature)

        for item in quirks:
            if item not in payload["board_specific_quirks"]:
                payload["board_specific_quirks"].append(item)

        if unsupported_format and unsupported_format not in payload["unsupported_formats"]:
            payload["unsupported_formats"].append(unsupported_format)

        for item in route_constraints:
            if item not in payload["route_specific_constraints"]:
                payload["route_specific_constraints"].append(item)

        for item in recovery_patterns:
            if item not in payload["recovery_patterns"]:
                payload["recovery_patterns"].append(item)

        if runtime_signature:
            serialized = json.dumps(dict(runtime_signature), sort_keys=True)
            existing = {
                json.dumps(item, sort_keys=True)
                for item in payload.get("runtime_signatures", [])
                if isinstance(item, dict)
            }
            if serialized not in existing:
                payload.setdefault("runtime_signatures", []).append(dict(runtime_signature))

        if failure_signature and failure_signature not in payload.get("failure_signatures", []):
            payload.setdefault("failure_signatures", []).append(failure_signature)

        payload["history"].append(
            {
                "run_id": run_id,
                "success": success,
                "asset_id": asset_id,
                "overlay": overlay,
                "failure_signature": failure_signature or "",
            }
        )
        self.save(payload)
        return payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_registry(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_REGISTRY
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("board") != "RB3Gen2":
        raise ValueError("registry_board_mismatch")
    return payload


def _resolve_repository_asset(path_text: str) -> Path:
    candidate = _repo_root() / path_text
    return candidate.resolve()


def _select_asset(
    registry: Mapping[str, Any],
    *,
    target: str,
    sample_rate_hz: int,
    channels: int,
    fmt: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in registry.get("assets", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("intended_playback_path", "")).startswith(target) or target in str(
            item.get("intended_playback_path", "")
        ):
            candidates.append(item)

    def score(asset: Mapping[str, Any]) -> tuple[int, int, int]:
        sr_match = 1 if int(asset.get("sample_rate_hz", 0)) == sample_rate_hz else 0
        ch_match = 1 if int(asset.get("channels", 0)) == channels else 0
        fmt_match = 1 if str(asset.get("format", "")).upper() == fmt.upper() else 0
        return (sr_match, ch_match, fmt_match)

    scored = sorted(candidates, key=score, reverse=True)
    for asset in scored:
        repo_path = _resolve_repository_asset(str(asset.get("repository_path", "")))
        if repo_path.exists():
            chosen = dict(asset)
            chosen["repository_path_abs"] = str(repo_path)
            chosen["sha256"] = _sha256_file(repo_path)
            chosen["exists"] = True
            return chosen

    return None


def stage_asset_to_bridge(
    asset: Mapping[str, Any],
    *,
    bridge_root: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Stage selected WAV to bridge share for Windows worker adb-push operation."""

    bridge = Path(bridge_root)
    src = Path(str(asset.get("repository_path_abs", "")))
    rel = str(asset.get("bridge_relative_path", "")).strip().replace("\\", "/")

    if not src.exists() or not src.is_file():
        return {
            "status": "INVALID",
            "reason": "source_asset_missing",
            "staged": False,
        }

    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return {
            "status": "INVALID",
            "reason": "bridge_relative_path_invalid",
            "staged": False,
        }

    dst = bridge / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not overwrite:
        return {
            "status": "BLOCKED",
            "reason": "bridge_stage_overwrite_blocked",
            "staged": False,
            "staged_path": str(dst),
        }

    shutil.copy2(src, dst)
    dst_hash = _sha256_file(dst)
    expected = str(asset.get("sha256", ""))
    if expected and dst_hash != expected:
        return {
            "status": "INVALID",
            "reason": "bridge_stage_checksum_mismatch",
            "staged": False,
            "staged_path": str(dst),
            "expected_sha256": expected,
            "actual_sha256": dst_hash,
        }

    return {
        "status": "STAGED",
        "reason": "ok",
        "staged": True,
        "staged_path": str(dst),
        "staged_sha256": dst_hash,
    }


def _infer_overlay(static_context: Mapping[str, Any], memory: Mapping[str, Any]) -> dict[str, Any]:
    candidates = list(static_context.get("overlay_inheritance", {}).get("overlay_candidates", []))
    if not candidates:
        return {
            "overlay": "UNRESOLVED",
            "status": "ADVISORY_ONLY",
            "reason": "overlay_candidates_missing",
        }

    successful = [
        str(item.get("overlay", ""))
        for item in memory.get("successful_playback_procedures", [])
        if isinstance(item, dict)
    ]
    for candidate in candidates:
        if candidate in successful:
            return {
                "overlay": candidate,
                "status": "RESOLVED",
                "reason": "memory_preferred",
            }

    if len(candidates) == 1:
        return {
            "overlay": candidates[0],
            "status": "RESOLVED",
            "reason": "single_candidate",
        }

    return {
        "overlay": "UNRESOLVED",
        "status": "ADVISORY_ONLY",
        "reason": "overlay_ambiguous",
        "candidates": candidates,
    }


def _infer_pcm_for_speaker(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    entries = fingerprint.get("audio_discovery", {}).get("pcm_entries", [])
    if not isinstance(entries, list):
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        direction = str(entry.get("direction", "")).lower()
        streams = int(entry.get("streams", 0))
        name = str(entry.get("name", "")).lower()
        iface = str(entry.get("interface", "")).lower()
        if direction != "playback" or streams < 1:
            continue
        if any(token in name or token in iface for token in ("primary", "speaker", "mm", "multimedia")):
            pcm_id = str(entry.get("pcm_id", ""))
            parts = pcm_id.split("-") if "-" in pcm_id else []
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return {
                    "pcm_id": pcm_id,
                    "alsa_device": f"hw:{parts[0]},{parts[1]}",
                    "confidence": "HIGH",
                    "source": "runtime_pcm_evidence",
                    "entry": entry,
                }

    cards = fingerprint.get("audio_discovery", {}).get("alsa_topology_cards", [])
    if isinstance(cards, list) and cards:
        card = cards[0]
        if isinstance(card, dict):
            idx = int(card.get("card_index", 0))
            return {
                "pcm_id": f"{idx:02d}-00",
                "alsa_device": f"hw:{idx},0",
                "confidence": "LOW",
                "source": "card_fallback",
                "entry": None,
            }

    return {
        "pcm_id": "UNKNOWN",
        "alsa_device": "UNKNOWN",
        "confidence": "LOW",
        "source": "insufficient_runtime_evidence",
        "entry": None,
    }


def _build_mixer_dependency_sequence(
    static_context: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
) -> dict[str, Any]:
    routing = static_context.get("qcom_audio_routing", [])
    if not isinstance(routing, list):
        routing = []

    dependencies: list[str] = []
    sequence: list[dict[str, str]] = []

    for item in routing:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        sink = str(item.get("sink", "")).strip()
        if not source or not sink:
            continue
        dependencies.append(f"{source}->{sink}")

    inferred_route = False
    if not dependencies:
        markers = [str(item).lower() for item in static_context.get("soundwire_topology_markers", [])]
        if any("wsa" in marker for marker in markers):
            dependencies.append("MultiMedia1->PRIMARY_MI2S_RX")
            dependencies.append("PRIMARY_MI2S_RX->WSA_SPKR")
            inferred_route = True

    if dependencies:
        sequence.append(
            {
                "step": "validate_route_topology",
                "classification": "SAFE_READ",
            }
        )
        sequence.append(
            {
                "step": "snapshot_mixer_state",
                "classification": "SAFE_READ",
            }
        )
        sequence.append(
            {
                "step": "apply_route_mixer_controls",
                "classification": "REQUIRES_OPERATOR_APPROVAL",
            }
        )
        sequence.append(
            {
                "step": "verify_dapm_route_activation",
                "classification": "SAFE_READ",
            }
        )
    else:
        sequence.append(
            {
                "step": "route_mapping_unresolved",
                "classification": "ADVISORY_ONLY",
            }
        )

    codec_nodes = static_context.get("codec_nodes", [])
    codec_activation = [
        str(item.get("compatible", ""))
        for item in codec_nodes
        if isinstance(item, dict)
    ]

    supports_tinymix = str(fingerprint.get("capabilities", {}).get("supports_tinymix", "UNKNOWN"))

    return {
        "route_dependencies": dependencies,
        "mixer_sequence": sequence,
        "codec_activation_candidates": codec_activation,
        "mixer_confidence": "MEDIUM" if dependencies and supports_tinymix != "UNSUPPORTED" else "LOW",
        "route_inferred": inferred_route,
    }


def _build_push_command(asset: Mapping[str, Any], target_path: str, overwrite_policy: str) -> str:
    return (
        "AURA_ADB_PUSH "
        f"{asset['bridge_relative_path']} "
        f"{target_path} "
        f"{asset['sha256']} "
        f"{overwrite_policy}"
    )


def _encode_amixer_name(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode("utf-8")).decode("ascii").rstrip("=")


def _build_amixer_name_set_command(name: str, value: str) -> str:
    return f"AURA_AMIXER_NAME_SET {_encode_amixer_name(name)} {value}"


def _seeded_mixer_apply_commands(overlay: str) -> list[str]:
    if overlay != RB3_AUDIOREACH_OVERLAY:
        return []
    return [_build_amixer_name_set_command(name, value) for name, value in RB3_OPERATOR_PROVEN_SPEAKER_SEQUENCE]


def _prefer_playback_alsa_device(alsa_device: str) -> str:
    if alsa_device.startswith("hw:"):
        return "plughw:" + alsa_device[3:]
    return alsa_device


def _runtime_validation_steps(alsa_device: str, target_path: str) -> list[dict[str, str]]:
    return [
        {"classification": "SAFE_READ", "command": "cat /proc/asound/cards"},
        {"classification": "SAFE_READ", "command": "cat /proc/asound/pcm"},
        {"classification": "SAFE_READ", "command": "tinymix"},
        {"classification": "SAFE_READ", "command": "amixer"},
        {"classification": "SAFE_READ", "command": "cat /sys/kernel/debug/asoc/*/dapm"},
        {"classification": "SAFE_READ", "command": "dmesg"},
        {
            "classification": "REQUIRES_OPERATOR_APPROVAL",
            "command": f"AURA_PLAYBACK_APLAY {alsa_device} {target_path}",
        },
        {"classification": "SAFE_READ", "command": "cat /proc/asound/pcm"},
        {"classification": "SAFE_READ", "command": "cat /sys/kernel/debug/asoc/*/dapm"},
        {"classification": "SAFE_READ", "command": "tinymix"},
        {"classification": "SAFE_READ", "command": "amixer"},
        {"classification": "SAFE_READ", "command": "dmesg"},
    ]


def build_audio_route_knowledge_graph(
    *,
    static_context: Mapping[str, Any],
    mixer_dependency: Mapping[str, Any],
    overlay: Mapping[str, Any],
    pcm_inference: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    nodes.append({"id": "board:RB3Gen2", "kind": "board", "label": "RB3Gen2"})

    ov = str(overlay.get("overlay", "UNRESOLVED"))
    nodes.append({"id": f"overlay:{ov}", "kind": "overlay", "label": ov})
    edges.append({"from": "board:RB3Gen2", "to": f"overlay:{ov}", "relation": "inherits"})

    for mapping in static_context.get("backend_frontend_mappings", []):
        if not isinstance(mapping, dict):
            continue
        fe = str(mapping.get("frontend", "")).strip()
        be = str(mapping.get("backend", "")).strip()
        if not fe or not be:
            continue
        fe_id = f"fe:{fe}"
        be_id = f"be:{be}"
        nodes.append({"id": fe_id, "kind": "frontend", "label": fe})
        nodes.append({"id": be_id, "kind": "backend", "label": be})
        edges.append({"from": fe_id, "to": be_id, "relation": "feeds"})

    for dep in mixer_dependency.get("route_dependencies", []):
        raw = str(dep)
        if "->" not in raw:
            continue
        source, sink = [part.strip() for part in raw.split("->", 1)]
        source_id = f"route:{source}"
        sink_id = f"route:{sink}"
        nodes.append({"id": source_id, "kind": "route_node", "label": source})
        nodes.append({"id": sink_id, "kind": "route_node", "label": sink})
        edges.append({"from": source_id, "to": sink_id, "relation": "route_dependency"})

    for codec in static_context.get("codec_nodes", []):
        if not isinstance(codec, dict):
            continue
        cid = f"codec:{codec.get('node', 'unknown')}"
        label = str(codec.get("compatible", "codec"))
        nodes.append({"id": cid, "kind": "codec", "label": label})
        edges.append({"from": "board:RB3Gen2", "to": cid, "relation": "codec_route"})

    for marker in static_context.get("soundwire_topology_markers", []):
        mk = str(marker)
        mid = f"soundwire:{mk}"
        nodes.append({"id": mid, "kind": "soundwire", "label": mk})
        edges.append({"from": "board:RB3Gen2", "to": mid, "relation": "soundwire_dependency"})

    alsa = str(pcm_inference.get("alsa_device", "UNKNOWN"))
    nodes.append({"id": f"pcm:{alsa}", "kind": "pcm", "label": alsa})
    edges.append({"from": "board:RB3Gen2", "to": f"pcm:{alsa}", "relation": "playback_topology"})

    dedup = {node["id"]: node for node in nodes}
    return {"nodes": list(dedup.values()), "edges": edges}


def build_playback_state_machine(
    plan: Mapping[str, Any],
    *,
    correlation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    states = [
        "asset_selected",
        "asset_deployed",
        "mixers_applied",
        "backend_enabled",
        "pcm_active",
        "playback_running",
        "playback_completed",
        "playback_failed",
        "cleanup_completed",
    ]
    transitions = [
        {"from": "asset_selected", "to": "asset_deployed", "condition": "deployment_success"},
        {"from": "asset_deployed", "to": "mixers_applied", "condition": "mixer_apply_success"},
        {"from": "mixers_applied", "to": "backend_enabled", "condition": "backend_activity_true"},
        {"from": "backend_enabled", "to": "pcm_active", "condition": "pcm_activation_true"},
        {"from": "pcm_active", "to": "playback_running", "condition": "playback_started"},
        {"from": "playback_running", "to": "playback_completed", "condition": "playback_exit_zero"},
        {"from": "playback_running", "to": "playback_failed", "condition": "playback_exit_nonzero"},
        {"from": "playback_completed", "to": "cleanup_completed", "condition": "cleanup_success"},
        {"from": "playback_failed", "to": "cleanup_completed", "condition": "cleanup_success_or_skipped"},
    ]

    deployment = plan.get("asset_deployment", {})
    current_state = "asset_selected"
    final_classification = "ADVISORY_ONLY"

    if deployment.get("staging", {}).get("staged", False):
        current_state = "asset_deployed"

    if correlation:
        if correlation.get("mixer_change"):
            current_state = "mixers_applied"
        if correlation.get("backend_activity"):
            current_state = "backend_enabled"
        if correlation.get("pcm_activation"):
            current_state = "pcm_active"
        if correlation.get("playback_started"):
            current_state = "playback_running"
        if correlation.get("playback_completion"):
            current_state = "playback_completed"
        elif correlation.get("playback_attempted"):
            current_state = "playback_failed"

        if correlation.get("cleanup_completed"):
            current_state = "cleanup_completed"

        if (
            correlation.get("playback_completion")
            and correlation.get("route_activation_confidence") == "HIGH"
            and correlation.get("cleanup_completed")
        ):
            final_classification = "CAPTURE_READY"
        elif correlation.get("playback_attempted"):
            final_classification = "ADVISORY_ONLY"

    return {
        "states": states,
        "transitions": transitions,
        "current_state": current_state,
        "final_classification": final_classification,
    }


def correlate_runtime_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Correlate runtime telemetry snapshots for playback validation reasoning."""

    def text(key: str) -> str:
        return str(evidence.get(key, ""))

    pcm_before = text("pcm_before")
    pcm_after = text("pcm_after")
    dmesg_before = text("dmesg_before")
    dmesg_after = text("dmesg_after")
    dapm_before = text("dapm_before")
    dapm_after = text("dapm_after")
    mixer_before = text("mixer_before")
    mixer_after = text("mixer_after")
    soundwire_before = text("soundwire_before")
    soundwire_after = text("soundwire_after")
    pcm_runtime_before = text("pcm_runtime_state_before")
    pcm_runtime_after = text("pcm_runtime_state_after")

    playback_exit_code = int(evidence.get("playback_exit_code", -1))
    playback_stderr = text("playback_stderr").lower()
    cleanup_exit_code = int(evidence.get("cleanup_exit_code", -1))

    pcm_activation = (pcm_before != pcm_after and bool(pcm_after.strip())) or (
        pcm_runtime_before != pcm_runtime_after and bool(pcm_runtime_after.strip())
    )
    backend_activity = (dmesg_before != dmesg_after) and any(
        token in dmesg_after.lower() for token in ("lpass", "asoc", "snd", "q6", "wsa", "tx", "rx")
    )
    dapm_state_change = dapm_before != dapm_after and bool(dapm_after.strip())
    mixer_change = mixer_before != mixer_after and bool(mixer_after.strip())
    soundwire_activity = (soundwire_before != soundwire_after) or any(
        token in dmesg_after.lower() for token in ("soundwire", "swr", "wsa")
    )

    playback_completion = playback_exit_code == 0 and "not found" not in playback_stderr
    playback_attempted = playback_exit_code != -1 or bool(playback_stderr)
    playback_started = playback_attempted and "no such file" not in playback_stderr
    cleanup_completed = cleanup_exit_code == 0

    if playback_completion and (pcm_activation or dapm_state_change or backend_activity or soundwire_activity):
        route_conf = "HIGH"
    elif playback_completion:
        route_conf = "MEDIUM"
    else:
        route_conf = "LOW"

    return {
        "pcm_activation": pcm_activation,
        "backend_activity": backend_activity,
        "dapm_state_change": dapm_state_change,
        "mixer_change": mixer_change,
        "soundwire_activity": soundwire_activity,
        "pcm_runtime_state_change": pcm_runtime_before != pcm_runtime_after,
        "pcm_runtime_state_before": pcm_runtime_before,
        "pcm_runtime_state_after": pcm_runtime_after,
        "playback_attempted": playback_attempted,
        "playback_started": playback_started,
        "playback_completion": playback_completion,
        "cleanup_completed": cleanup_completed,
        "route_activation_confidence": route_conf,
        "evidence_quality": "HIGH"
        if all([pcm_after, dmesg_after, dapm_after])
        else "MEDIUM"
        if any([pcm_after, dmesg_after, dapm_after])
        else "LOW",
    }


def explain_playback_failure(
    plan: Mapping[str, Any],
    correlation: Mapping[str, Any],
    *,
    static_context: Mapping[str, Any],
) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []

    if plan.get("overlay", {}).get("overlay") == "UNRESOLVED":
        reasons.append(
            {
                "code": "unsupported_overlay",
                "why": "No supported overlay was resolved for RB3Gen2 speaker playback path.",
            }
        )

    if plan.get("overlay", {}).get("status") != "RESOLVED":
        reasons.append(
            {
                "code": "overlay_mismatch",
                "why": "Overlay selection is unresolved or ambiguous.",
            }
        )

    if not static_context.get("backend_frontend_mappings") and not plan.get("mixer_dependency", {}).get("route_dependencies"):
        reasons.append(
            {
                "code": "unresolved_routes",
                "why": "No backend/frontend route mapping was extracted from DTS routing evidence.",
            }
        )

    if not plan.get("mixer_dependency", {}).get("route_dependencies"):
        reasons.append(
            {
                "code": "missing_mixers",
                "why": "Mixer dependency graph does not contain route dependencies.",
            }
        )
    elif correlation.get("mixer_change") is False:
        reasons.append(
            {
                "code": "missing_mixer",
                "why": "No runtime mixer state change was observed while playback workflow was attempted.",
            }
        )

    if not correlation.get("backend_activity"):
        reasons.append(
            {
                "code": "missing_backend",
                "why": "Runtime telemetry did not show backend activity during playback validation.",
            }
        )
        reasons.append(
            {
                "code": "unsupported_backend",
                "why": "Runtime telemetry did not show backend activity during playback validation.",
            }
        )

    soundwire_markers = static_context.get("soundwire_topology_markers", [])
    if soundwire_markers and not (correlation.get("dapm_state_change") or correlation.get("soundwire_activity")):
        reasons.append(
            {
                "code": "soundwire_dependency_failure",
                "why": "SoundWire-related topology markers exist but DAPM route activation was not observed.",
            }
        )

    if not correlation.get("pcm_activation"):
        reasons.append(
            {
                "code": "invalid_pcm",
                "why": "PCM runtime state did not become active for the planned playback path.",
            }
        )

    if correlation.get("playback_started") and not correlation.get("route_activation_confidence") == "HIGH":
        reasons.append(
            {
                "code": "route_collapse",
                "why": "Playback started but route activation confidence did not reach HIGH.",
            }
        )

    if not correlation.get("playback_completion"):
        reasons.append(
            {
                "code": "playback_not_completed",
                "why": "Playback command did not complete successfully.",
            }
        )

    if not reasons:
        reasons.append(
            {
                "code": "no_failure_detected",
                "why": "Evidence does not indicate a failure condition.",
            }
        )

    return {
        "failure_reasons": reasons,
        "classification": "ADVISORY_ONLY" if any(r["code"] != "no_failure_detected" for r in reasons) else "CAPTURE_READY",
    }


def build_rb3_speaker_playback_plan(
    fingerprint: Mapping[str, Any],
    *,
    static_context: Mapping[str, Any],
    memory: Mapping[str, Any],
    bridge_root: str | Path,
    intent: str = "validate speaker playback",
    target_path: str = "/data/local/tmp/aura/audio/speaker_validation.wav",
    overwrite_policy: str = "no_overwrite",
    sample_rate_hz: int = 48000,
    channels: int = 2,
    fmt: str = "S16_LE",
    registry_path: str | Path | None = None,
    stage_asset: bool = True,
) -> RB3PlaybackPlanResult:
    if intent.strip().lower() != "validate speaker playback":
        return RB3PlaybackPlanResult(
            plan={
                "board": "RB3Gen2",
                "intent": intent,
                "classification": "REJECTED",
                "reason": "unsupported_intent",
                "governance_posture": "ADVISORY_ONLY",
            }
        )

    registry = _read_registry(registry_path)
    overlay = _infer_overlay(static_context, memory)
    pcm = _infer_pcm_for_speaker(fingerprint)
    mixer_dependency = _build_mixer_dependency_sequence(static_context, fingerprint)

    selected_asset = _select_asset(
        registry,
        target="speaker",
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        fmt=fmt,
    )

    deployment: dict[str, Any] = {
        "asset_selected": selected_asset is not None,
        "overwrite_policy": overwrite_policy,
        "target_path": target_path,
        "requires_operator_approval": True,
        "deployment_status": "ADVISORY_ONLY",
        "staging": {
            "status": "NOT_ATTEMPTED",
            "staged": False,
        },
    }

    if selected_asset is not None:
        deployment["selected_asset"] = selected_asset
        if stage_asset:
            staging = stage_asset_to_bridge(
                selected_asset,
                bridge_root=bridge_root,
                overwrite=overwrite_policy == "allow_overwrite",
            )
            deployment["staging"] = staging
            push_command = _build_push_command(selected_asset, target_path, overwrite_policy)
            deployment["push_command"] = push_command
            if staging.get("staged"):
                deployment["deployment_status"] = "READY_FOR_OPERATOR_APPROVAL"
            else:
                if str(staging.get("status", "")).upper() == "BLOCKED":
                    deployment["deployment_status"] = "BLOCKED"
                else:
                    deployment["deployment_status"] = "ADVISORY_ONLY"

    targeted_questions: list[dict[str, str]] = []
    runtime_confidence = str(fingerprint.get("environment", {}).get("confidence", "LOW"))
    if runtime_confidence in {"LOW", "MEDIUM"}:
        targeted_questions.append(
            {
                "id": "runtime_profile",
                "question": "Runtime confidence is not high. Confirm active audio runtime profile for RB3 speaker path validation.",
            }
        )
    if overlay.get("status") != "RESOLVED":
        targeted_questions.append(
            {
                "id": "overlay_selection",
                "question": "Select active RB3Gen2 audio overlay before playback activation.",
            }
        )
    if pcm.get("alsa_device") == "UNKNOWN":
        targeted_questions.append(
            {
                "id": "pcm_selection",
                "question": "Playback PCM is unresolved; provide confirmed ALSA device (e.g. hw:0,0).",
            }
        )
    if selected_asset is None:
        targeted_questions.append(
            {
                "id": "asset_availability",
                "question": "No compatible WAV asset exists in the registry path. Provide staged RB3Gen2 speaker WAV.",
            }
        )
    if not mixer_dependency.get("route_dependencies"):
        targeted_questions.append(
            {
                "id": "route_mapping",
                "question": "Backend/frontend route mapping is unresolved; provide confirmed speaker route chain.",
            }
        )
    elif mixer_dependency.get("route_inferred"):
        targeted_questions.append(
            {
                "id": "route_confirmation",
                "question": "Route chain was inferred from SoundWire markers. Confirm `MultiMedia1 -> PRIMARY_MI2S_RX -> WSA_SPKR` before mixer activation.",
            }
        )
    playback_alsa_device = _prefer_playback_alsa_device(str(pcm.get("alsa_device", "UNKNOWN")))
    playback_command = f"AURA_PLAYBACK_APLAY {playback_alsa_device} {target_path}"
    remembered_sequences = [
        item
        for item in memory.get("successful_playback_procedures", [])
        if isinstance(item, dict)
    ]
    mixer_apply_commands: list[str] = []
    mixer_sequence_source = "none"
    for item in remembered_sequences:
        if str(item.get("overlay", "")) == str(overlay.get("overlay", "")):
            sequence = item.get("mixer_sequence", [])
            if isinstance(sequence, list) and sequence:
                mixer_apply_commands = [str(cmd) for cmd in sequence]
                mixer_sequence_source = "procedural_memory_success"
                break
    if not mixer_apply_commands:
        mixer_apply_commands = _seeded_mixer_apply_commands(str(overlay.get("overlay", "")))
        if mixer_apply_commands:
            mixer_sequence_source = "operator_proven_seeded_sequence"
    if mixer_apply_commands:
        mixer_dependency["operator_mixer_apply_commands"] = mixer_apply_commands
        mixer_dependency["operator_mixer_apply_sequence_source"] = mixer_sequence_source
    else:
        targeted_questions.append(
            {
                "id": "mixer_sequence_seed",
                "question": "No proven mixer apply sequence is stored yet. Provide operator-approved `AURA_TINYMIX_SET`/`AURA_AMIXER_CSET`/`AURA_AMIXER_NAME_SET` sequence for first run.",
            }
        )
    route_knowledge_graph = build_audio_route_knowledge_graph(
        static_context=static_context,
        mixer_dependency=mixer_dependency,
        overlay=overlay,
        pcm_inference=pcm,
    )

    plan: dict[str, Any] = {
        "board": "RB3Gen2",
        "intent": "validate speaker playback",
        "overlay": overlay,
        "pcm_inference": pcm,
        "mixer_dependency": mixer_dependency,
        "asset_deployment": deployment,
        "playback_workflow": {
            "required_overlay": overlay.get("overlay", "UNRESOLVED"),
            "mixer_sequence": mixer_dependency.get("mixer_sequence", []),
            "playback_pcm": pcm,
            "playback_alsa_device": playback_alsa_device,
            "compatible_asset": selected_asset,
            "deployment_path": target_path,
            "playback_command": playback_command,
            "cleanup_command": f"AURA_ADB_RM {target_path}",
            "mixer_apply_commands": mixer_apply_commands,
            "mixer_apply_sequence_source": mixer_sequence_source,
            "runtime_validation_steps": _runtime_validation_steps(playback_alsa_device, target_path),
            "runtime_telemetry_correlation": [
                "pcm_activation",
                "backend_activity",
                "dapm_state_change",
                "dmesg_delta",
                "mixer_state_change",
                "soundwire_activity",
                "playback_completion",
            ],
        },
        "audio_route_knowledge_graph": route_knowledge_graph,
        "procedural_memory_hints": {
            "preferred_assets": memory.get("successful_wav_assets", []),
            "known_quirks": memory.get("board_specific_quirks", []),
            "route_constraints": memory.get("route_specific_constraints", []),
            "recovery_patterns": memory.get("recovery_patterns", []),
            "runtime_signatures": memory.get("runtime_signatures", []),
            "failure_signatures": memory.get("failure_signatures", []),
        },
        "targeted_questions": targeted_questions,
        "state_machine": {},
        "classification": "ADVISORY_ONLY",
        "governance": {
            "linux_role": "authoritative_governance_and_cognition",
            "windows_role": "execution_only_worker",
            "fail_closed": True,
            "evidence_backed_planning_only": True,
            "no_hallucinated_assets": True,
            "no_unsafe_writes": True,
        },
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }

    plan["state_machine"] = build_playback_state_machine(plan)
    return RB3PlaybackPlanResult(plan=plan)
