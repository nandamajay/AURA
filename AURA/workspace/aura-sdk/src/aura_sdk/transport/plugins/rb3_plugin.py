"""RB3 target plugin implementing the portable target plugin contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.dts_audio_cognition import parse_dts_audio_cognition
from aura_sdk.transport.rb3_playback_cognition import (
    RB3ProceduralMemory,
    build_rb3_speaker_playback_plan,
    correlate_runtime_evidence,
    explain_playback_failure,
)


def _stable_hash(payload: Mapping[str, Any]) -> str:
    data = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _text_corpus(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True).lower()


class RB3TargetPlugin:
    """RB3 target intelligence isolated from generic runtime orchestration."""

    target_id = "RB3Gen2"

    def topology_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        entry_dts = str(payload.get("entry_dts", "")).strip()
        if entry_dts and Path(entry_dts).exists():
            static_context = parse_dts_audio_cognition(entry_dts, max_include_depth=6).context
        else:
            static_context = {
                "entry_dts": "UNAVAILABLE",
                "source_files": [],
                "include_graph": [],
                "unresolved_includes": [],
                "sound_card_nodes": [],
                "dai_links": [],
                "backend_frontend_mappings": [],
                "qcom_audio_routing": [],
                "soundwire_topology_markers": [],
                "codec_nodes": [],
                "overlay_inheritance": {"overlay_candidates": [], "ambiguous": True},
                "widgets": [],
                "parse_confidence": "LOW",
                "governance_posture": "ADVISORY_ONLY",
            }

        return {
            "target_id": self.target_id,
            "provider": "rb3.topology_provider",
            "static_context": static_context,
            "topology_fingerprint": _stable_hash(
                {
                    "overlay": static_context.get("overlay_inheritance", {}),
                    "dai_links": static_context.get("dai_links", []),
                    "routing": static_context.get("qcom_audio_routing", []),
                    "soundwire": static_context.get("soundwire_topology_markers", []),
                }
            ),
        }

    def mixer_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        capabilities = _as_dict(fingerprint.get("capabilities"))
        audio = _as_dict(fingerprint.get("audio_discovery"))
        amixer_controls = _as_list(audio.get("amixer_controls"))
        tinymix_controls = _as_list(audio.get("tinymix_controls"))

        return {
            "target_id": self.target_id,
            "provider": "rb3.mixer_provider",
            "supports_amixer": str(capabilities.get("supports_amixer", "UNKNOWN")),
            "supports_tinymix": str(capabilities.get("supports_tinymix", "UNKNOWN")),
            "amixer_control_count": len(amixer_controls),
            "tinymix_control_count": len(tinymix_controls),
            "mixer_controls_fingerprint": _stable_hash(
                {
                    "amixer_controls": amixer_controls,
                    "tinymix_controls": tinymix_controls,
                }
            ),
        }

    def pcm_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        audio = _as_dict(fingerprint.get("audio_discovery"))
        pcm_entries = _as_list(audio.get("pcm_entries"))

        return {
            "target_id": self.target_id,
            "provider": "rb3.pcm_provider",
            "pcm_entries": pcm_entries,
            "pcm_names": [str(item.get("name", "")) for item in pcm_entries if isinstance(item, dict)],
            "pcm_signature": _stable_hash({"pcm_entries": pcm_entries}),
        }

    def route_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "route_summary")).strip() or "route_summary"
        if mode == "playback_workflow":
            fingerprint = _as_dict(payload.get("fingerprint"))
            topology = self.topology_provider(payload)
            static_context = _as_dict(topology.get("static_context"))

            memory_payload = _as_dict(payload.get("memory"))
            memory_path = str(payload.get("memory_path", "")).strip()
            if not memory_payload and memory_path:
                memory_payload = RB3ProceduralMemory(memory_path).load()
            if not memory_payload:
                memory_payload = RB3ProceduralMemory(Path("/tmp") / "rb3_plugin_memory.json").load()

            bridge_root = str(payload.get("bridge_root", "")).strip() or "/tmp"
            plan = build_rb3_speaker_playback_plan(
                fingerprint,
                static_context=static_context,
                memory=memory_payload,
                bridge_root=bridge_root,
                intent=str(payload.get("intent", "validate speaker playback")),
                target_path=str(payload.get("target_path", "/data/local/tmp/aura/audio/speaker_validation.wav")),
                overwrite_policy=str(payload.get("overwrite_policy", "no_overwrite")),
                sample_rate_hz=int(payload.get("sample_rate_hz", 48000)),
                channels=int(payload.get("channels", 2)),
                fmt=str(payload.get("fmt", "S16_LE")),
                stage_asset=bool(payload.get("stage_asset", True)),
            ).plan
            return {
                "target_id": self.target_id,
                "provider": "rb3.route_provider",
                "mode": mode,
                "workflow": plan,
                "route_fingerprint": _stable_hash(
                    {
                        "overlay": _as_dict(plan.get("overlay")),
                        "pcm": _as_dict(plan.get("pcm_inference")),
                        "mixer": _as_dict(plan.get("mixer_dependency")),
                    }
                ),
            }

        static_context = _as_dict(payload.get("static_context"))
        return {
            "target_id": self.target_id,
            "provider": "rb3.route_provider",
            "mode": mode,
            "backend_frontend_mappings": _as_list(static_context.get("backend_frontend_mappings")),
            "qcom_audio_routing": _as_list(static_context.get("qcom_audio_routing")),
            "route_fingerprint": _stable_hash(
                {
                    "backend_frontend_mappings": _as_list(static_context.get("backend_frontend_mappings")),
                    "qcom_audio_routing": _as_list(static_context.get("qcom_audio_routing")),
                }
            ),
        }

    def evidence_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "runtime_correlation")).strip() or "runtime_correlation"

        if mode == "runtime_correlation":
            correlation = correlate_runtime_evidence(_as_dict(payload.get("runtime_evidence")))
            return {
                "target_id": self.target_id,
                "provider": "rb3.evidence_provider",
                "mode": mode,
                "runtime_correlation": correlation,
                "evidence_quality": "HIGH" if correlation.get("playback_completion") else "MEDIUM",
            }

        if mode == "failure_explanation":
            explanation = explain_playback_failure(
                _as_dict(payload.get("plan")),
                _as_dict(payload.get("runtime_correlation")),
                static_context=_as_dict(payload.get("static_context")),
            )
            return {
                "target_id": self.target_id,
                "provider": "rb3.evidence_provider",
                "mode": mode,
                "failure_explanation": explanation,
            }

        evidence = _as_dict(payload.get("runtime_evidence"))
        return {
            "target_id": self.target_id,
            "provider": "rb3.evidence_provider",
            "mode": mode,
            "evidence_fingerprint": _stable_hash(evidence),
        }

    def capability_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        capabilities = _as_dict(fingerprint.get("capabilities"))
        discovery = _as_dict(fingerprint.get("audio_discovery"))

        corpus = _text_corpus(fingerprint)
        markers = ("rb3gen2", "qcs6490", "qcm6490")
        marker_hits = [marker for marker in markers if marker in corpus]

        rb3_flag = bool(discovery.get("rb3gen2_detected"))
        amixer_supported = str(capabilities.get("supports_amixer", "UNKNOWN")) == "SUPPORTED"
        tinymix_supported = str(capabilities.get("supports_tinymix", "UNKNOWN")) == "SUPPORTED"

        confidence = 0.0
        if rb3_flag:
            confidence += 0.45
        if marker_hits:
            confidence += 0.35
        if amixer_supported or tinymix_supported:
            confidence += 0.20
        confidence = round(min(1.0, confidence), 3)

        supported = rb3_flag or bool(marker_hits)
        return {
            "target_id": self.target_id,
            "provider": "rb3.capability_provider",
            "supported": supported,
            "confidence": confidence,
            "marker_hits": marker_hits,
            "rb3_flag": rb3_flag,
            "mixer_capabilities": {
                "supports_amixer": str(capabilities.get("supports_amixer", "UNKNOWN")),
                "supports_tinymix": str(capabilities.get("supports_tinymix", "UNKNOWN")),
            },
            "replay_contract_requirements": [
                "execution_ordering",
                "timing_windows",
                "route_fingerprint",
                "pcm_signature",
                "evidence_sequence",
                "cleanup_sequence",
            ],
        }

    def validation_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "plugin_health")).strip() or "plugin_health"

        if mode == "replay_compatibility":
            contract = _as_dict(payload.get("replay_contract"))
            sequence = _as_list(contract.get("sequence_contract"))
            required = {
                "execution_ordering",
                "timing_windows",
                "route_fingerprint",
                "pcm_signature",
                "evidence_sequence",
                "cleanup_sequence",
            }
            present = {str(item).strip() for item in sequence if str(item).strip()}
            missing = sorted(required.difference(present))
            if not missing:
                level = "FULL"
            elif len(missing) <= 2:
                level = "PARTIAL"
            else:
                level = "INCOMPATIBLE"
            return {
                "target_id": self.target_id,
                "provider": "rb3.validation_provider",
                "mode": mode,
                "compatibility_level": level,
                "missing_contract_elements": missing,
                "deterministic": True,
            }

        if mode == "governance_boundary":
            governance = _as_dict(payload.get("governance_state"))
            autonomous_flags = [
                bool(governance.get("autonomous_patching_allowed", False)),
                bool(governance.get("autonomous_topology_rewrite_allowed", False)),
                bool(governance.get("autonomous_mixer_mutation_allowed", False)),
                bool(governance.get("autonomous_upstream_generation_allowed", False)),
            ]
            violations = sum(1 for item in autonomous_flags if item)
            return {
                "target_id": self.target_id,
                "provider": "rb3.validation_provider",
                "mode": mode,
                "governance_boundary_ok": violations == 0,
                "classification": "PASS" if violations == 0 else "FAIL_CLOSED",
                "violations": violations,
            }

        return {
            "target_id": self.target_id,
            "provider": "rb3.validation_provider",
            "mode": mode,
            "health": "OK",
        }


def get_plugin() -> RB3TargetPlugin:
    return RB3TargetPlugin()
