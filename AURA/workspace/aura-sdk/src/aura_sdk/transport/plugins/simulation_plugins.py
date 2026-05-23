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
