"""RB3 target plugin implementing the portable target plugin contract."""

from __future__ import annotations

import hashlib
import json
import re
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


def _read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


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

    def dts_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        entry_dts = str(payload.get("entry_dts", "")).strip()
        static_context = _as_dict(payload.get("static_context"))
        if not static_context and entry_dts and Path(entry_dts).exists():
            static_context = parse_dts_audio_cognition(entry_dts, max_include_depth=6).context

        entry_text = _read_text(entry_dts) if entry_dts else ""
        include_graph = _as_list(static_context.get("include_graph"))
        source_files = [str(item) for item in _as_list(static_context.get("source_files")) if str(item).strip()]
        overlay_candidates = _as_list(_as_dict(static_context.get("overlay_inheritance")).get("overlay_candidates"))
        overlay_hierarchy = [str(item.get("path", "")) for item in include_graph if isinstance(item, dict)]

        nodes = _as_list(static_context.get("sound_card_nodes"))
        vendor_only_nodes = [
            str(item.get("node", item))
            for item in nodes
            if "qcom" in str(item).lower() or "qcs" in str(item).lower() or "msm" in str(item).lower()
        ]
        reusable_nodes = [
            str(item.get("node", item))
            for item in nodes
            if str(item.get("node", item)).strip() and str(item.get("node", item)) not in vendor_only_nodes
        ]

        fe_be_routes = _as_list(static_context.get("backend_frontend_mappings"))
        codec_bindings = _as_list(static_context.get("codec_nodes"))

        clock_deps = sorted(set(re.findall(r"\bclocks?\b", entry_text, flags=re.IGNORECASE)))
        regulator_deps = sorted(set(re.findall(r"\bregulators?\b", entry_text, flags=re.IGNORECASE)))
        gpio_deps = sorted(set(re.findall(r"\bgpios?\b", entry_text, flags=re.IGNORECASE)))

        payload_obj = {
            "overlay_hierarchy": overlay_hierarchy,
            "overlay_candidates": [str(item) for item in overlay_candidates],
            "vendor_only_nodes": vendor_only_nodes,
            "reusable_upstream_nodes": reusable_nodes,
            "fe_be_route_topology": fe_be_routes,
            "codec_bindings": codec_bindings,
            "dependencies": {
                "clocks": clock_deps,
                "regulators": regulator_deps,
                "gpios": gpio_deps,
            },
            "source_files": source_files,
        }
        return {
            "target_id": self.target_id,
            "provider": "rb3.dts_adapter",
            "semantic_dts": payload_obj,
            "fingerprint": _stable_hash(payload_obj),
        }

    def topology_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        static_context = _as_dict(payload.get("static_context"))
        if not static_context and str(payload.get("entry_dts", "")).strip():
            static_context = self.topology_provider(payload).get("static_context", {})
        routes = _as_list(static_context.get("qcom_audio_routing"))
        fe_be = _as_list(static_context.get("backend_frontend_mappings"))
        soundwire = _as_list(static_context.get("soundwire_topology_markers"))
        graph = {
            "routes": routes,
            "frontend_backend": fe_be,
            "soundwire_markers": soundwire,
        }
        return {
            "target_id": self.target_id,
            "provider": "rb3.topology_adapter",
            "topology_graph": graph,
            "fingerprint": _stable_hash(graph),
        }

    def vendor_api_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        driver_context = str(payload.get("driver_context", ""))
        lowered = driver_context.lower()
        downstream_only_apis = sorted(
            {
                token
                for token in (
                    "msm_",
                    "qcom_",
                    "snd_soc_qcom_",
                    "wcd9",
                    "audioreach",
                )
                if token in lowered
            }
        )
        vendor_hooks = sorted(
            {
                token
                for token in (
                    "vendor_hook",
                    "trace_android_vh",
                    "qcom_snd",
                    "msm_pcm",
                )
                if token in lowered
            }
        )
        wrapper_layers = sorted(
            {
                token
                for token in (
                    "wrapper",
                    "compat_layer",
                    "shim",
                )
                if token in lowered
            }
        )
        duplicated_vendor_abstractions = bool("abstract" in lowered and "vendor" in lowered)
        codec_coupling = "wcd" in lowered or "codec" in lowered
        platform_assumptions = sorted({item for item in ("qcs6490", "rb3gen2", "msm") if item in lowered})
        subsystem_ownership = "audio" if any(token in lowered for token in ("snd", "audio", "codec")) else "unknown"

        payload_obj = {
            "downstream_only_apis": downstream_only_apis,
            "vendor_hooks": vendor_hooks,
            "wrapper_layers": wrapper_layers,
            "duplicated_vendor_abstractions": duplicated_vendor_abstractions,
            "codec_coupling": codec_coupling,
            "platform_assumptions": platform_assumptions,
            "subsystem_ownership": subsystem_ownership,
        }
        return {
            "target_id": self.target_id,
            "provider": "rb3.vendor_api_adapter",
            "semantic_driver": payload_obj,
            "fingerprint": _stable_hash(payload_obj),
        }

    def subsystem_descriptor_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        static_context = _as_dict(payload.get("static_context"))
        descriptors = {
            "audio": {
                "owner": "alsa_asoc",
                "topology_markers": _as_list(static_context.get("soundwire_topology_markers")),
                "codec_nodes": _as_list(static_context.get("codec_nodes")),
            },
            "device_tree": {
                "owner": "dts_overlay",
                "overlay_candidates": _as_list(_as_dict(static_context.get("overlay_inheritance")).get("overlay_candidates")),
                "source_count": len(_as_list(static_context.get("source_files"))),
            },
        }
        return {
            "target_id": self.target_id,
            "provider": "rb3.subsystem_descriptor_provider",
            "descriptors": descriptors,
            "fingerprint": _stable_hash(descriptors),
        }

    def runtime_evidence_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        runtime = _as_dict(payload.get("runtime_evidence"))
        pcm = _as_dict(payload.get("pcm_activity"))
        mixer = _as_dict(payload.get("mixer_state"))
        replay = _as_dict(payload.get("replay_traces"))
        governance = _as_dict(payload.get("governance_decisions"))

        playback_success = bool(runtime.get("playback_completion", False) or runtime.get("process_success", False))
        if not playback_success and runtime.get("playback_exit_code") == 0:
            playback_success = True

        normalized_runtime = {
            "run_id": str(runtime.get("run_id", runtime.get("trace_id", ""))),
            "process_success": bool(runtime.get("process_success", playback_success)),
            "evidence_success": bool(runtime.get("evidence_success", False)),
            "playback_completion": playback_success,
            "classification": str(runtime.get("classification", "UNKNOWN")),
            "runtime_fingerprint": _stable_hash(runtime),
            "evidence_references": [str(item) for item in _as_list(runtime.get("evidence_references")) if str(item).strip()],
        }

        normalized_pcm = {
            "pcm_signature": str(pcm.get("pcm_signature", pcm.get("signature_sha256", ""))),
            "active_paths": _as_list(pcm.get("active_paths")),
            "pcm_entries": _as_list(pcm.get("pcm_entries")),
            "pcm_fingerprint": _stable_hash(pcm),
        }

        normalized_mixer = {
            "mixer_controls": _as_list(mixer.get("controls")),
            "active_switches": _as_list(mixer.get("active_switches")),
            "mixer_fingerprint": _stable_hash(mixer),
        }

        normalized_replay = {
            "deterministic_event_ordering": bool(
                replay.get("deterministic_event_ordering", bool(replay.get("deterministic_replay_fingerprint", "")))
            ),
            "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
        }

        return {
            "target_id": self.target_id,
            "provider": "rb3.runtime_evidence_adapter",
            "runtime_evidence": normalized_runtime,
            "pcm_activity": normalized_pcm,
            "mixer_state": normalized_mixer,
            "replay_traces": normalized_replay,
            "governance_decisions": governance,
            "fingerprint": _stable_hash(
                {
                    "runtime": normalized_runtime,
                    "pcm": normalized_pcm,
                    "mixer": normalized_mixer,
                    "replay": normalized_replay,
                    "governance": governance,
                }
            ),
        }

    def topology_evidence_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        topology = _as_dict(payload.get("topology_cognition"))
        dts = _as_dict(payload.get("dts_cognition"))
        capabilities = _as_dict(payload.get("plugin_capability_state"))

        normalized_topology = {
            "confidence": _as_dict(topology.get("confidence")),
            "runtime_route_graph": _as_dict(topology.get("runtime_route_graph")),
            "procedural_route_memory": _as_dict(topology.get("procedural_route_memory")),
            "topology_fingerprint": _stable_hash(topology),
        }
        normalized_dts = {
            "overlay_inheritance": _as_dict(dts.get("overlay_inheritance", dts)),
            "backend_frontend_mappings": _as_list(dts.get("backend_frontend_mappings")),
            "qcom_audio_routing": _as_list(dts.get("qcom_audio_routing")),
            "soundwire_topology_markers": _as_list(dts.get("soundwire_topology_markers")),
            "dts_fingerprint": _stable_hash(dts),
        }

        return {
            "target_id": self.target_id,
            "provider": "rb3.topology_evidence_adapter",
            "topology_cognition": normalized_topology,
            "dts_cognition": normalized_dts,
            "plugin_capability_state": capabilities,
            "fingerprint": _stable_hash(
                {
                    "topology": normalized_topology,
                    "dts": normalized_dts,
                    "capabilities": capabilities,
                }
            ),
        }

    def semantic_evidence_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        semantic = _as_dict(payload.get("semantic_cognition"))
        regressions = [item for item in _as_list(payload.get("regression_history")) if isinstance(item, dict)]
        capabilities = _as_dict(payload.get("plugin_capability_state"))

        normalized_semantic = {
            "classification": _as_dict(semantic.get("classification")),
            "semantic_fingerprint": str(semantic.get("semantic_fingerprint", "")),
            "artifacts": _as_dict(semantic.get("artifacts")),
            "evidence_references": [str(item) for item in _as_list(semantic.get("evidence_references")) if str(item).strip()],
        }

        return {
            "target_id": self.target_id,
            "provider": "rb3.semantic_evidence_adapter",
            "semantic_cognition": normalized_semantic,
            "regression_history": regressions,
            "plugin_capability_state": capabilities,
            "fingerprint": _stable_hash(
                {
                    "semantic": normalized_semantic,
                    "regressions": regressions,
                    "capabilities": capabilities,
                }
            ),
        }

    def downstream_upstream_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        semantic = _as_dict(payload.get("semantic_cognition"))
        adapters = _as_dict(semantic.get("adapters"))
        driver = _as_dict(_as_dict(adapters.get("vendor_api")).get("semantic_driver"))
        constructs = sorted(
            {
                str(item)
                for key in ("downstream_only_apis", "vendor_hooks", "wrapper_layers")
                for item in _as_list(driver.get(key))
                if str(item).strip()
            }
        )

        upstream_equivalents = {
            "msm_": "snd_soc_component_*",
            "qcom_": "asoc_generic_component_*",
            "snd_soc_qcom_": "snd_soc_*",
            "msm_pcm": "soc_pcm_runtime_helpers",
            "vendor_hook": "tracepoint_or_standard_callback",
            "wrapper": "asoc_helper_layer",
        }

        confidence = {
            key: 0.82 if value != "UNRESOLVED" else 0.25 for key, value in upstream_equivalents.items()
        }

        # Preserve unmapped constructs with conservative confidence.
        for item in constructs:
            upstream_equivalents.setdefault(item, "UNRESOLVED")
            confidence.setdefault(item, 0.3)

        return {
            "target_id": self.target_id,
            "provider": "rb3.downstream_upstream_adapter",
            "vendor_constructs": constructs,
            "upstream_equivalents": upstream_equivalents,
            "equivalence_confidence": confidence,
            "fingerprint": _stable_hash(
                {
                    "vendor_constructs": constructs,
                    "upstream_equivalents": upstream_equivalents,
                    "equivalence_confidence": confidence,
                }
            ),
        }

    def topology_translation_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        topology = _as_dict(payload.get("topology_cognition"))
        dts = _as_dict(payload.get("dts_cognition"))
        runtime = _as_dict(payload.get("runtime_evidence"))

        fe_be_routes = [
            str(item)
            for item in _as_list(dts.get("backend_frontend_mappings"))
            if str(item).strip()
        ]
        if not fe_be_routes:
            fe_be_routes = [
                str(item)
                for item in _as_list(_as_dict(topology.get("runtime_route_graph")).get("runtime_paths"))
                if str(item).strip()
            ]

        vendor_abstractions = [
            str(item)
            for item in _as_list(dts.get("qcom_audio_routing"))
            if str(item).strip()
        ]

        expected_sequence = [
            str(item)
            for item in _as_list(runtime.get("command_sequence"))
            if str(item).strip()
        ]

        return {
            "target_id": self.target_id,
            "provider": "rb3.topology_translation_adapter",
            "fe_be_routes": fe_be_routes,
            "vendor_topology_abstractions": vendor_abstractions,
            "pcm_nodes": [str(item) for item in _as_list(_as_dict(topology.get("procedural_route_memory")).get("stable_pcm_fingerprints")) if str(item).strip()],
            "dpcm_links": fe_be_routes,
            "route_fingerprint": str(runtime.get("route_fingerprint", "")),
            "expected_sequence": expected_sequence,
            "fingerprint": _stable_hash(
                {
                    "fe_be_routes": fe_be_routes,
                    "vendor_topology_abstractions": vendor_abstractions,
                    "route_fingerprint": str(runtime.get("route_fingerprint", "")),
                }
            ),
        }

    def runtime_conversion_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        runtime = _as_dict(payload.get("runtime_evidence"))
        capabilities = _as_dict(payload.get("plugin_capability_state"))
        governance = _as_dict(payload.get("governance_state"))

        deps = [
            "vendor_amixer_sequence",
            "vendor_route_fingerprint",
            "vendor_codec_dependency",
        ]
        replay_safe = [
            "normalize_mixer_control_aliases",
            "normalize_route_chain_labels",
            "derive_generic_asoc_identifiers",
        ]
        advisory = [
            "manual_codec_binding_review",
            "manual_dai_link_reconciliation",
        ]
        expected_sequence = [
            "collect_runtime_evidence",
            "apply_route_translation",
            "validate_pcm_activation",
            "validate_replay_compatibility",
            "finalize_governed_plan",
        ]
        forbidden = [
            "autonomous_code_rewrite",
            "autonomous_dts_mutation",
            "autonomous_driver_mutation",
            "unsafe_topology_mutation",
        ]

        return {
            "target_id": self.target_id,
            "provider": "rb3.runtime_conversion_adapter",
            "downstream_runtime_dependencies": deps,
            "replay_safe_transformations": replay_safe,
            "advisory_only_transformations": advisory,
            "forbidden_autonomous_transformations": forbidden,
            "required_capabilities": _as_dict(capabilities.get("capabilities", capabilities)),
            "expected_runtime_seconds": 25.0,
            "expected_sequence": expected_sequence,
            "governance": governance,
            "fingerprint": _stable_hash(
                {
                    "dependencies": deps,
                    "replay_safe_transformations": replay_safe,
                    "advisory_only_transformations": advisory,
                    "forbidden_autonomous_transformations": forbidden,
                    "expected_runtime_seconds": 25.0,
                    "expected_sequence": expected_sequence,
                }
            ),
        }


def get_plugin() -> RB3TargetPlugin:
    return RB3TargetPlugin()
