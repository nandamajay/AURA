"""Cross-target simulation plugins for portable runtime stabilization.

These plugins are synthetic and do not require hardware.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


class _BaseSimulationPlugin:
    target_id = "unknown"
    health = "DEGRADED"
    supports_topology = True
    replay_mode = "FULL"

    def topology_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not self.supports_topology:
            return {
                "target_id": self.target_id,
                "provider": f"{self.target_id}.topology_provider",
                "status": "UNSUPPORTED",
                "topology_fingerprint": "",
            }
        topology = {
            "dai_links": [f"{self.target_id}:fe0->be0"],
            "routing": [f"{self.target_id}:PCM0->SPKR"],
            "status": self.health,
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.topology_provider",
            "status": "SUPPORTED",
            "topology": topology,
            "topology_fingerprint": _hash(topology),
        }

    def mixer_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        capabilities = _as_dict(fingerprint.get("capabilities"))
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.mixer_provider",
            "supports_amixer": str(capabilities.get("supports_amixer", "UNKNOWN")),
            "supports_tinymix": str(capabilities.get("supports_tinymix", "UNKNOWN")),
            "health": self.health,
        }

    def pcm_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        audio = _as_dict(fingerprint.get("audio_discovery"))
        entries = _as_list(audio.get("pcm_entries"))
        if not entries:
            entries = [{"pcm_id": "00-00", "name": "SimPCM0", "direction": "playback", "streams": 1}]
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.pcm_provider",
            "pcm_entries": entries,
            "pcm_signature": _hash({"pcm_entries": entries}),
        }

    def route_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        workflow = {
            "classification": "ADVISORY_ONLY",
            "route_steps": ["resolve_pcm", "resolve_backend", "validate_route", "ready"],
            "health": self.health,
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.route_provider",
            "workflow": workflow,
            "route_fingerprint": _hash(workflow),
        }

    def evidence_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        evidence = _as_dict(payload.get("runtime_evidence"))
        quality = "LOW" if self.health == "DEGRADED" else "HIGH"
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.evidence_provider",
            "evidence_mode": "simulated",
            "evidence_quality": quality,
            "evidence_fingerprint": _hash(evidence),
        }

    def capability_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = _as_dict(payload.get("fingerprint"))
        caps = _as_dict(fingerprint.get("capabilities"))

        conflict = bool(fingerprint.get("capability_conflict", False))
        degraded = bool(fingerprint.get("degraded_capabilities", False))
        missing = not bool(caps)
        base_conf = 0.85
        if missing:
            base_conf -= 0.55
        if degraded:
            base_conf -= 0.35
        if conflict:
            base_conf -= 0.65
        conf = round(max(0.0, min(1.0, base_conf)), 3)

        supported = conf >= 0.35 and not conflict
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.capability_provider",
            "supported": supported,
            "confidence": conf,
            "missing_capabilities": missing,
            "conflicting_capabilities": conflict,
            "degraded_runtime": degraded,
        }

    def validation_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "plugin_health")).strip() or "plugin_health"
        if mode == "replay_compatibility":
            sequence = _as_list(_as_dict(payload.get("replay_contract")).get("sequence_contract"))
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

            if self.replay_mode == "INCOMPATIBLE":
                level = "INCOMPATIBLE"
            elif self.replay_mode == "PARTIAL":
                level = "PARTIAL" if len(missing) <= 3 else "INCOMPATIBLE"
            else:
                level = "FULL" if not missing else "PARTIAL"

            return {
                "target_id": self.target_id,
                "provider": f"{self.target_id}.validation_provider",
                "mode": mode,
                "compatibility_level": level,
                "missing_contract_elements": missing,
                "deterministic": True,
            }
        if mode == "governance_boundary":
            governance = _as_dict(payload.get("governance_state"))
            violations = int(
                bool(governance.get("autonomous_patching_allowed", False))
                or bool(governance.get("autonomous_topology_rewrite_allowed", False))
                or bool(governance.get("autonomous_mixer_mutation_allowed", False))
                or bool(governance.get("autonomous_upstream_generation_allowed", False))
            )
            return {
                "target_id": self.target_id,
                "provider": f"{self.target_id}.validation_provider",
                "mode": mode,
                "governance_boundary_ok": violations == 0,
                "classification": "PASS" if violations == 0 else "FAIL_CLOSED",
            }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.validation_provider",
            "mode": mode,
            "health": self.health,
        }

    def dts_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        semantic = {
            "overlay_hierarchy": [f"{self.target_id}.dtsi"],
            "vendor_only_nodes": [f"{self.target_id}:vendor_node"] if self.health == "DEGRADED" else [],
            "reusable_upstream_nodes": [f"{self.target_id}:generic_audio_node"],
            "fe_be_route_topology": [f"{self.target_id}:fe0->be0"],
            "codec_bindings": [f"{self.target_id}:codec0"],
            "dependencies": {
                "clocks": ["clk_audio_core"],
                "regulators": ["vdd_audio"],
                "gpios": ["gpio_spkr_en"],
            },
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.dts_adapter",
            "semantic_dts": semantic,
            "fingerprint": _hash(semantic),
        }

    def topology_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        topology = {
            "routes": [f"{self.target_id}:pcm0->spkr"],
            "frontend_backend": [f"{self.target_id}:fe0->be0"],
            "topology_state": self.health,
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.topology_adapter",
            "topology_graph": topology,
            "fingerprint": _hash(topology),
        }

    def vendor_api_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self.target_id == "fake_target_alpha":
            driver = {
                "downstream_only_apis": [],
                "vendor_hooks": [],
                "wrapper_layers": [],
                "duplicated_vendor_abstractions": False,
                "codec_coupling": False,
                "platform_assumptions": [],
                "subsystem_ownership": "audio",
            }
        elif self.target_id == "fake_target_beta":
            driver = {
                "downstream_only_apis": ["vendor_beta_wrap"],
                "vendor_hooks": ["vendor_hook_beta"],
                "wrapper_layers": ["beta_shim"],
                "duplicated_vendor_abstractions": False,
                "codec_coupling": True,
                "platform_assumptions": ["beta_soc"],
                "subsystem_ownership": "audio",
            }
        else:
            driver = {
                "downstream_only_apis": ["gamma_vendor_api"],
                "vendor_hooks": ["vendor_hook_gamma"],
                "wrapper_layers": ["gamma_shim"],
                "duplicated_vendor_abstractions": True,
                "codec_coupling": True,
                "platform_assumptions": ["gamma_soc"],
                "subsystem_ownership": "audio",
            }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.vendor_api_adapter",
            "semantic_driver": driver,
            "fingerprint": _hash(driver),
        }

    def subsystem_descriptor_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        descriptors = {
            "audio": {
                "owner": "simulated",
                "state": self.health,
            },
            "platform": {
                "owner": self.target_id,
                "portable": self.target_id != "degraded_target_gamma",
            },
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.subsystem_descriptor_provider",
            "descriptors": descriptors,
            "fingerprint": _hash(descriptors),
        }

    def runtime_evidence_adapter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        runtime = _as_dict(payload.get("runtime_evidence"))
        pcm = _as_dict(payload.get("pcm_activity"))
        mixer = _as_dict(payload.get("mixer_state"))
        replay = _as_dict(payload.get("replay_traces"))
        governance = _as_dict(payload.get("governance_decisions"))

        normalized_runtime = {
            "run_id": str(runtime.get("run_id", f"{self.target_id}-sim-run")),
            "process_success": bool(runtime.get("process_success", self.health != "DEGRADED")),
            "playback_completion": bool(runtime.get("playback_completion", self.health != "DEGRADED")),
            "classification": str(runtime.get("classification", "ADVISORY_ONLY")),
            "runtime_fingerprint": _hash(runtime),
        }
        normalized_pcm = {
            "pcm_signature": str(pcm.get("pcm_signature", _hash(pcm))),
            "active_paths": _as_list(pcm.get("active_paths")),
            "pcm_entries": _as_list(pcm.get("pcm_entries")),
            "pcm_fingerprint": _hash(pcm),
        }
        normalized_mixer = {
            "controls": _as_list(mixer.get("controls")),
            "active_switches": _as_list(mixer.get("active_switches")),
            "mixer_fingerprint": _hash(mixer),
        }
        normalized_replay = {
            "deterministic_event_ordering": bool(
                replay.get("deterministic_event_ordering", bool(replay.get("deterministic_replay_fingerprint", "")))
            ),
            "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
        }

        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.runtime_evidence_adapter",
            "runtime_evidence": normalized_runtime,
            "pcm_activity": normalized_pcm,
            "mixer_state": normalized_mixer,
            "replay_traces": normalized_replay,
            "governance_decisions": governance,
            "fingerprint": _hash(
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
            "topology_fingerprint": _hash(topology),
        }
        normalized_dts = {
            "overlay_inheritance": _as_dict(dts.get("overlay_inheritance")),
            "backend_frontend_mappings": _as_list(dts.get("backend_frontend_mappings")),
            "qcom_audio_routing": _as_list(dts.get("qcom_audio_routing")),
            "soundwire_topology_markers": _as_list(dts.get("soundwire_topology_markers")),
            "dts_fingerprint": _hash(dts),
        }
        return {
            "target_id": self.target_id,
            "provider": f"{self.target_id}.topology_evidence_adapter",
            "topology_cognition": normalized_topology,
            "dts_cognition": normalized_dts,
            "plugin_capability_state": capabilities,
            "fingerprint": _hash(
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
            "provider": f"{self.target_id}.semantic_evidence_adapter",
            "semantic_cognition": normalized_semantic,
            "regression_history": regressions,
            "plugin_capability_state": capabilities,
            "fingerprint": _hash(
                {
                    "semantic": normalized_semantic,
                    "regressions": regressions,
                    "capabilities": capabilities,
                }
            ),
        }


class FakeTargetAlphaPlugin(_BaseSimulationPlugin):
    target_id = "fake_target_alpha"
    health = "HEALTHY"
    supports_topology = True
    replay_mode = "FULL"


class FakeTargetBetaPlugin(_BaseSimulationPlugin):
    target_id = "fake_target_beta"
    health = "HEALTHY"
    supports_topology = True
    replay_mode = "PARTIAL"


class DegradedTargetGammaPlugin(_BaseSimulationPlugin):
    target_id = "degraded_target_gamma"
    health = "DEGRADED"
    supports_topology = False
    replay_mode = "INCOMPATIBLE"

    def capability_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = super().capability_provider(payload)
        result["supported"] = False
        result["confidence"] = min(float(result.get("confidence", 0.0)), 0.2)
        return result


class InvalidQuarantinedPlugin:
    """Intentionally invalid plugin (missing required provider methods)."""

    target_id = "invalid_target_quarantined"


class TopologyErrorPlugin(_BaseSimulationPlugin):
    target_id = "unsupported_topology_delta"

    def topology_provider(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("topology_provider_not_supported")


def get_fake_target_alpha_plugin() -> FakeTargetAlphaPlugin:
    return FakeTargetAlphaPlugin()


def get_fake_target_beta_plugin() -> FakeTargetBetaPlugin:
    return FakeTargetBetaPlugin()


def get_degraded_target_gamma_plugin() -> DegradedTargetGammaPlugin:
    return DegradedTargetGammaPlugin()


def get_invalid_quarantined_plugin() -> InvalidQuarantinedPlugin:
    return InvalidQuarantinedPlugin()


def get_topology_error_plugin() -> TopologyErrorPlugin:
    return TopologyErrorPlugin()


def build_simulation_registry_payload() -> dict[str, Any]:
    module = "aura_sdk.transport.plugins.simulation_plugins"
    return {
        "schema_version": "1.0",
        "registry_name": "aura_simulation_plugin_registry",
        "plugins": [
            {
                "target_id": "fake_target_alpha",
                "entrypoint": f"{module}:get_fake_target_alpha_plugin",
                "priority": 100,
                "detection": {
                    "text_markers": ["alpha"],
                    "audio_discovery_flags": [],
                    "required_capabilities": ["supports_amixer"],
                },
            },
            {
                "target_id": "fake_target_beta",
                "entrypoint": f"{module}:get_fake_target_beta_plugin",
                "priority": 90,
                "detection": {
                    "text_markers": ["beta"],
                    "audio_discovery_flags": [],
                    "required_capabilities": ["supports_tinymix"],
                },
            },
            {
                "target_id": "degraded_target_gamma",
                "entrypoint": f"{module}:get_degraded_target_gamma_plugin",
                "priority": 80,
                "detection": {
                    "text_markers": ["gamma"],
                    "audio_discovery_flags": [],
                    "required_capabilities": ["supports_amixer"],
                },
            },
            {
                "target_id": "unsupported_topology_delta",
                "entrypoint": f"{module}:get_topology_error_plugin",
                "priority": 70,
                "detection": {
                    "text_markers": ["delta"],
                    "audio_discovery_flags": [],
                    "required_capabilities": ["supports_amixer"],
                },
            },
            {
                "target_id": "invalid_target_quarantined",
                "entrypoint": f"{module}:get_invalid_quarantined_plugin",
                "priority": 60,
                "detection": {
                    "text_markers": ["invalid"],
                    "audio_discovery_flags": [],
                    "required_capabilities": [],
                },
            },
        ],
    }
