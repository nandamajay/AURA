"""Portable target runtime layer using plugin contracts.

This module is intentionally generic and contains no target-specific branching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.plugins import PluginNegotiationRequest, TargetPluginLoader


@dataclass(frozen=True)
class PortableRuntimeWorkflowResult:
    classification: str
    target_id: str
    negotiation: dict[str, Any]
    topology: dict[str, Any]
    mixer: dict[str, Any]
    pcm: dict[str, Any]
    route: dict[str, Any]
    evidence: dict[str, Any]
    replay_compatibility: dict[str, Any]


class PortableRuntimeLayer:
    """Generic orchestration facade for target plugin execution."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def negotiate_target(
        self,
        *,
        fingerprint: Mapping[str, Any],
        target_profile: Mapping[str, Any] | None,
        capability_registry: Mapping[str, Any] | None,
        governance_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        request = PluginNegotiationRequest(
            fingerprint=dict(fingerprint),
            target_profile=dict(target_profile or {}),
            capability_registry=dict(capability_registry or {}),
            governance_state=dict(governance_state or {}),
        )
        result = self._plugins.negotiate(request)
        return {
            "classification": result.classification,
            "selected_target_id": result.selected_target_id,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "candidate_scores": result.candidate_scores,
            "governance_posture": result.governance_posture,
        }

    def build_workflow(
        self,
        *,
        fingerprint: Mapping[str, Any],
        target_profile: Mapping[str, Any] | None = None,
        capability_registry: Mapping[str, Any] | None = None,
        governance_state: Mapping[str, Any] | None = None,
        entry_dts: str | None = None,
        memory: Mapping[str, Any] | None = None,
        memory_path: str | None = None,
        bridge_root: str | None = None,
        intent: str = "validate speaker playback",
        target_path: str = "/data/local/tmp/aura/audio/speaker_validation.wav",
        overwrite_policy: str = "no_overwrite",
        replay_contract: Mapping[str, Any] | None = None,
    ) -> PortableRuntimeWorkflowResult:
        negotiation = self.negotiate_target(
            fingerprint=fingerprint,
            target_profile=target_profile,
            capability_registry=capability_registry,
            governance_state=governance_state,
        )

        classification = str(negotiation.get("classification", "FAIL_CLOSED"))
        target_id = str(negotiation.get("selected_target_id", ""))
        if classification != "COMPATIBLE" or not target_id:
            empty: dict[str, Any] = {}
            return PortableRuntimeWorkflowResult(
                classification=classification,
                target_id=target_id,
                negotiation=negotiation,
                topology=empty,
                mixer=empty,
                pcm=empty,
                route=empty,
                evidence=empty,
                replay_compatibility={
                    "validation_type": "deterministic_plugin_replay_compatibility",
                    "compatibility_level": "INCOMPATIBLE",
                    "classification": "FAIL_CLOSED",
                },
            )

        plugin = self._plugins.load_plugin(target_id)
        topology = plugin.topology_provider({"entry_dts": entry_dts})
        mixer = plugin.mixer_provider({"fingerprint": dict(fingerprint)})
        pcm = plugin.pcm_provider({"fingerprint": dict(fingerprint)})
        route = plugin.route_provider(
            {
                "mode": "playback_workflow",
                "fingerprint": dict(fingerprint),
                "entry_dts": entry_dts,
                "static_context": topology.get("static_context", {}),
                "memory": dict(memory or {}),
                "memory_path": memory_path,
                "bridge_root": bridge_root,
                "intent": intent,
                "target_path": target_path,
                "overwrite_policy": overwrite_policy,
                "stage_asset": True,
            }
        )

        runtime_evidence = {
            "playback_exit_code": 0,
            "playback_stderr": "",
            "pcm_before": "",
            "pcm_after": "",
            "mixer_before": "",
            "mixer_after": "",
        }
        evidence = plugin.evidence_provider(
            {
                "mode": "runtime_correlation",
                "runtime_evidence": runtime_evidence,
            }
        )

        replay_compat = self._plugins.validate_replay_compatibility(
            target_id=target_id,
            replay_contract=dict(replay_contract or {}),
        )

        return PortableRuntimeWorkflowResult(
            classification="COMPATIBLE",
            target_id=target_id,
            negotiation=negotiation,
            topology=topology,
            mixer=mixer,
            pcm=pcm,
            route=route,
            evidence=evidence,
            replay_compatibility=replay_compat,
        )
