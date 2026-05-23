#!/usr/bin/env python3
"""Generate portable multi-target cognition architecture artifacts.

This phase is architecture-only: no autonomous mutation, no patching, no
runtime topology rewriting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _portable_target_cognition_architecture() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "phase": "PORTABLE_MULTI_TARGET_COGNITION",
        "reference_target": {
            "target_id": "RB3Gen2",
            "role": "known_good_reference",
            "baseline_registry": "rb3gen2_audible_baseline_registry.json",
        },
        "design_principles": [
            "registry_first_state",
            "runtime_evidence_truth",
            "cognition_as_interpretation",
            "governance_as_enforcement",
            "deterministic_replay_required",
            "fail_closed_default",
            "no_hidden_prompt_memory_dependency",
        ],
        "portability_objective": {
            "scope": "multi_qualcomm_targets",
            "in_scope": [
                "target_identity_abstraction",
                "overlay_identity_abstraction",
                "pcm_topology_abstraction",
                "backend_route_abstraction",
                "runtime_evidence_abstraction",
                "mixer_capability_abstraction",
                "capability_discovery_and_confidence",
            ],
            "out_of_scope": [
                "autonomous_patching",
                "autonomous_upstream_generation",
                "autonomous_topology_rewriting",
                "autonomous_mixer_mutation",
            ],
        },
        "execution_posture": {
            "mode": "advisory_or_governed_only",
            "write_policy": "governed_write_approved_only",
            "fail_closed": True,
        },
        "generated_at_epoch": time.time(),
    }


def _cognition_abstraction_layer() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "layer_name": "AURA_Cognition_Abstraction_Layer",
        "contracts": [
            {
                "interface": "TargetIdentityProvider",
                "responsibility": "resolve target board/soc identity from runtime evidence",
                "inputs": ["runtime_capability_report", "bootloader_identity", "kernel_identity"],
                "outputs": ["target_identity", "target_identity_confidence"],
            },
            {
                "interface": "OverlayIdentityProvider",
                "responsibility": "resolve base/overlay lineage and mutations",
                "inputs": ["entry_dts", "overlay_chain", "runtime_overlay_evidence"],
                "outputs": ["overlay_identity", "overlay_mutation_fingerprint"],
            },
            {
                "interface": "PCMTopologyProvider",
                "responsibility": "normalize ALSA FE/BE/PCM topology across targets",
                "inputs": ["proc_asound_cards", "proc_asound_pcm", "dai_link_evidence"],
                "outputs": ["pcm_topology_model", "pcm_topology_confidence"],
            },
            {
                "interface": "BackendRoutingProvider",
                "responsibility": "map runtime playback/capture chains to backend routes",
                "inputs": ["runtime_route_graph", "mixer_state", "dapm_or_equivalent"],
                "outputs": ["backend_route_model", "route_fingerprint"],
            },
            {
                "interface": "RuntimeEvidenceProvider",
                "responsibility": "classify and quality-score evidence availability",
                "inputs": ["trace", "event_lineage", "transport_metrics", "artifact_index"],
                "outputs": ["runtime_evidence_profile", "evidence_quality_score"],
            },
            {
                "interface": "MixerCapabilityProvider",
                "responsibility": "discover and normalize mixer tool/control availability",
                "inputs": ["supports_amixer", "supports_tinymix", "mixer_outputs"],
                "outputs": ["mixer_capability_profile", "mixer_capability_confidence"],
            },
            {
                "interface": "TargetCapabilityScorer",
                "responsibility": "compute evidence-backed target confidence",
                "inputs": [
                    "target_identity_confidence",
                    "pcm_topology_confidence",
                    "route_confidence",
                    "evidence_quality_score",
                    "transport_stability",
                ],
                "outputs": ["target_capability_confidence", "confidence_breakdown"],
            },
            {
                "interface": "DeterministicReplayAdapter",
                "responsibility": "bind target profile to replay-safe procedural contract",
                "inputs": ["portable_target_profile", "procedural_memory", "governance_state"],
                "outputs": ["replay_contract", "compatibility_verdict"],
            },
        ],
        "constraints": {
            "no_autonomous_mutation": True,
            "no_prompt_memory_assumptions": True,
            "governance_gate_required_for_execution": True,
        },
        "generated_at_epoch": time.time(),
    }


def _target_profile_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PortableTargetCognitionProfile",
        "type": "object",
        "required": [
            "schema_version",
            "target_identity",
            "overlay_identity",
            "pcm_topology",
            "backend_routing",
            "runtime_evidence",
            "mixer_capabilities",
            "capability_discovery",
            "confidence",
            "governance",
            "replay_contract",
            "classification",
        ],
        "properties": {
            "schema_version": {"type": "string"},
            "target_identity": {
                "type": "object",
                "required": ["target_id", "soc_family", "board_variant", "identity_confidence"],
                "properties": {
                    "target_id": {"type": "string"},
                    "soc_family": {"type": "string"},
                    "board_variant": {"type": "string"},
                    "kernel_release": {"type": "string"},
                    "identity_evidence": {"type": "array", "items": {"type": "string"}},
                    "identity_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "overlay_identity": {
                "type": "object",
                "required": ["base_dtsi", "overlay_chain", "mutation_fingerprint"],
                "properties": {
                    "base_dtsi": {"type": "string"},
                    "overlay_chain": {"type": "array", "items": {"type": "string"}},
                    "mutation_fingerprint": {"type": "string"},
                    "overlay_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "pcm_topology": {
                "type": "object",
                "required": ["cards", "pcm_devices", "fe_nodes", "be_nodes", "topology_fingerprint"],
                "properties": {
                    "cards": {"type": "array", "items": {"type": "string"}},
                    "pcm_devices": {"type": "array", "items": {"type": "string"}},
                    "fe_nodes": {"type": "array", "items": {"type": "string"}},
                    "be_nodes": {"type": "array", "items": {"type": "string"}},
                    "dai_links": {"type": "array", "items": {"type": "string"}},
                    "topology_fingerprint": {"type": "string"},
                    "topology_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "backend_routing": {
                "type": "object",
                "required": ["playback_routes", "capture_routes", "route_fingerprint"],
                "properties": {
                    "playback_routes": {"type": "array", "items": {"type": "string"}},
                    "capture_routes": {"type": "array", "items": {"type": "string"}},
                    "active_backend_chain": {"type": "array", "items": {"type": "string"}},
                    "route_fingerprint": {"type": "string"},
                    "route_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "runtime_evidence": {
                "type": "object",
                "required": ["evidence_mode", "availability", "quality_score"],
                "properties": {
                    "evidence_mode": {"type": "string", "enum": ["governed_runtime", "offline_replay", "partial"]},
                    "availability": {
                        "type": "object",
                        "properties": {
                            "proc_asound": {"type": "boolean"},
                            "mixer_snapshot": {"type": "boolean"},
                            "event_lineage": {"type": "boolean"},
                            "runtime_trace": {"type": "boolean"},
                            "transport_metrics": {"type": "boolean"},
                        },
                    },
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "quality_score": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "mixer_capabilities": {
                "type": "object",
                "required": ["supports_amixer", "supports_tinymix", "capability_confidence"],
                "properties": {
                    "supports_amixer": {"type": "string", "enum": ["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]},
                    "supports_tinymix": {"type": "string", "enum": ["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]},
                    "controls_snapshot_fingerprint": {"type": "string"},
                    "capability_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "capability_discovery": {
                "type": "object",
                "required": ["discovery_method", "discovery_confidence", "unsupported_features"],
                "properties": {
                    "discovery_method": {"type": "string"},
                    "discovery_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "unsupported_features": {"type": "array", "items": {"type": "string"}},
                },
            },
            "confidence": {
                "type": "object",
                "required": [
                    "target_capability_confidence",
                    "topology_confidence",
                    "replay_confidence",
                    "evidence_confidence",
                ],
                "properties": {
                    "target_capability_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "topology_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "replay_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence_lineage_id": {"type": "string"},
                },
            },
            "governance": {
                "type": "object",
                "required": ["fail_closed", "execution_posture", "autonomous_mutation_allowed"],
                "properties": {
                    "fail_closed": {"type": "boolean"},
                    "execution_posture": {"type": "string", "enum": ["ADVISORY_ONLY", "GOVERNED_ONLY"]},
                    "autonomous_mutation_allowed": {"type": "boolean", "const": False},
                },
            },
            "replay_contract": {
                "type": "object",
                "required": ["deterministic_replay_required", "sequence_contract", "compatibility_level"],
                "properties": {
                    "deterministic_replay_required": {"type": "boolean"},
                    "sequence_contract": {"type": "array", "items": {"type": "string"}},
                    "compatibility_level": {"type": "string", "enum": ["FULL", "PARTIAL", "INCOMPATIBLE"]},
                },
            },
            "classification": {
                "type": "object",
                "required": ["process_success", "evidence_success", "audible_human_validation", "final_classification"],
                "properties": {
                    "process_success": {"type": "boolean"},
                    "evidence_success": {"type": "boolean"},
                    "audible_human_validation": {"type": "string"},
                    "final_classification": {"type": "string"},
                },
            },
        },
        "additionalProperties": False,
    }


def _runtime_capability_negotiation_model() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "model_name": "Portable_Runtime_Capability_Negotiation",
        "state_machine": {
            "states": [
                "target_identified",
                "capabilities_discovered",
                "evidence_profiled",
                "profile_matched",
                "replay_contract_negotiated",
                "governance_validated",
                "execution_advisory_or_governed",
            ],
            "transitions": [
                "target_identified->capabilities_discovered",
                "capabilities_discovered->evidence_profiled",
                "evidence_profiled->profile_matched",
                "profile_matched->replay_contract_negotiated",
                "replay_contract_negotiated->governance_validated",
                "governance_validated->execution_advisory_or_governed",
            ],
        },
        "negotiation_rules": [
            {
                "rule": "missing_runtime_evidence",
                "effect": "confidence_drop",
                "deterministic_effect": "reduce_by_fixed_weights",
            },
            {
                "rule": "unsupported_tool_detected",
                "effect": "degrade_capability",
                "deterministic_effect": "mark_feature_unsupported_no_guessing",
            },
            {
                "rule": "profile_schema_mismatch",
                "effect": "fail_closed",
                "deterministic_effect": "classification_invalid",
            },
            {
                "rule": "governance_policy_violation",
                "effect": "fail_closed",
                "deterministic_effect": "block_execution",
            },
        ],
        "confidence_scoring": {
            "weights": {
                "target_identity": 0.2,
                "topology": 0.25,
                "route": 0.2,
                "runtime_evidence": 0.2,
                "transport_stability": 0.15,
            },
            "constraints": [
                "confidence_monotonic_with_evidence_quality",
                "missing_evidence_never_increases_confidence",
                "unsupported_features_lower_confidence_deterministically",
            ],
        },
        "generated_at_epoch": time.time(),
    }


def _deterministic_replay_compatibility_strategy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "strategy_name": "Cross_Target_Deterministic_Replay_Compatibility",
        "rb3_reference_contract": {
            "target": "RB3Gen2",
            "profile_id": "audible_25s_speaker_v1",
            "contract_elements": [
                "execution_ordering",
                "timing_windows",
                "route_fingerprint",
                "pcm_signature",
                "evidence_sequence",
                "cleanup_sequence",
            ],
        },
        "compatibility_levels": [
            {
                "level": "FULL",
                "requirements": [
                    "matching_sequence_contract",
                    "stable_route_fingerprint",
                    "stable_pcm_mapping",
                    "governance_pass",
                ],
            },
            {
                "level": "PARTIAL",
                "requirements": [
                    "sequence_contract_adapted",
                    "evidence_quality_above_threshold",
                    "no_policy_violation",
                ],
                "restrictions": ["advisory_only_execution"],
            },
            {
                "level": "INCOMPATIBLE",
                "requirements": ["policy_violation_or_missing_core_contract"],
                "restrictions": ["fail_closed"],
            },
        ],
        "determinism_guards": [
            "event_ordering_validation",
            "replay_state_equivalence",
            "confidence_integrity_validation",
            "event_quarantine_enforcement",
        ],
        "generated_at_epoch": time.time(),
    }


def _migration_plan() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plan_name": "RB3_to_Portable_Cognition_Migration",
        "reference_target": "RB3Gen2",
        "phases": [
            {
                "phase": 0,
                "name": "RB3_reference_freeze",
                "deliverables": [
                    "freeze_rb3_profile_contract",
                    "freeze_rb3_procedural_memory_contract",
                    "freeze_rb3_governance_contract",
                ],
                "exit_criteria": ["rb3_contracts_versioned"],
            },
            {
                "phase": 1,
                "name": "introduce_abstraction_interfaces",
                "deliverables": [
                    "target_identity_interface",
                    "overlay_identity_interface",
                    "pcm_topology_interface",
                    "backend_routing_interface",
                    "runtime_evidence_interface",
                    "mixer_capability_interface",
                ],
                "exit_criteria": ["interfaces_mapped_to_rb3_reference"],
            },
            {
                "phase": 2,
                "name": "portable_profile_schema_adoption",
                "deliverables": [
                    "portable_target_profile_schema",
                    "schema_validators",
                    "compatibility_mapping_from_rb3",
                ],
                "exit_criteria": ["rb3_profile_transcoded_losslessly"],
            },
            {
                "phase": 3,
                "name": "capability_negotiation_and_confidence",
                "deliverables": [
                    "runtime_capability_negotiation_model",
                    "deterministic_confidence_formula",
                    "unsupported_feature_degradation_rules",
                ],
                "exit_criteria": ["confidence_integrity_tests_pass"],
            },
            {
                "phase": 4,
                "name": "cross_target_validation_enablement",
                "deliverables": [
                    "new_target_onboarding_checklist",
                    "replay_compatibility_matrix",
                    "governance_boundary_tests",
                ],
                "exit_criteria": ["at_least_one_non_rb3_target_validated_in_advisory_mode"],
            },
        ],
        "non_goals": [
            "autonomous_patch_submission",
            "autonomous_topology_rewriting",
            "unsupervised_runtime_mutation",
        ],
        "generated_at_epoch": time.time(),
    }


def _validation_strategy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "strategy_name": "Portable_Target_Validation_Strategy",
        "validation_tracks": [
            {
                "track": "target_discovery",
                "checks": [
                    "identity_resolution_consistency",
                    "overlay_chain_resolution",
                    "capability_discovery_repeatability",
                ],
            },
            {
                "track": "topology_and_route",
                "checks": [
                    "pcm_topology_normalization",
                    "backend_route_correlation",
                    "route_fingerprint_stability",
                ],
            },
            {
                "track": "determinism_and_replay",
                "checks": [
                    "event_ordering_stability",
                    "replay_state_equivalence",
                    "procedural_memory_consistency",
                    "baseline_equivalence",
                ],
            },
            {
                "track": "governance_and_safety",
                "checks": [
                    "fail_closed_policy_enforcement",
                    "event_quarantine_stability",
                    "confidence_integrity",
                    "cross_target_boundary_enforcement",
                ],
            },
        ],
        "entry_gate_for_new_target": [
            "portable_profile_schema_valid",
            "governance_state_loaded",
            "no_autonomous_features_enabled",
            "advisory_or_governed_execution_only",
        ],
        "exit_gate_for_new_target": [
            "replay_stability_score>=0.95",
            "topology_consistency_score>=0.90",
            "confidence_integrity_score>=0.95",
            "governance_integrity_score==1.0",
        ],
        "generated_at_epoch": time.time(),
    }


def _governance_boundaries() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "boundary_name": "Cross_Target_Governance_Boundaries",
        "global_constraints": {
            "fail_closed_default": True,
            "execution_posture": "ADVISORY_ONLY_OR_GOVERNED_ONLY",
            "runtime_evidence_truth_required": True,
            "cognition_without_evidence_forbidden": True,
            "autonomous_patching_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_mixer_mutation_allowed": False,
        },
        "cross_target_reasoning_rules": [
            {
                "rule": "no_unverified_target_transfer",
                "description": "Route/procedural assumptions cannot transfer across targets without evidence-backed mapping.",
            },
            {
                "rule": "confidence_is_target_scoped",
                "description": "Confidence evolution must be tracked per target_id + overlay identity.",
            },
            {
                "rule": "policy_violation_is_terminal",
                "description": "Any cross-target policy violation causes immediate fail-closed classification.",
            },
            {
                "rule": "advisory_first_for_new_target",
                "description": "New targets remain advisory until deterministic validation criteria pass.",
            },
        ],
        "required_artifacts": [
            "portable_target_profile",
            "capability_discovery_report",
            "replay_compatibility_report",
            "confidence_integrity_report",
            "governance_validation_report",
        ],
        "generated_at_epoch": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate portable target cognition architecture artifacts")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, dict[str, Any]] = {
        "portable_target_cognition_architecture.json": _portable_target_cognition_architecture(),
        "cognition_abstraction_layer.json": _cognition_abstraction_layer(),
        "target_profile_schema.json": _target_profile_schema(),
        "runtime_capability_negotiation_model.json": _runtime_capability_negotiation_model(),
        "deterministic_replay_compatibility_strategy.json": _deterministic_replay_compatibility_strategy(),
        "rb3_to_portable_migration_plan.json": _migration_plan(),
        "new_target_validation_strategy.json": _validation_strategy(),
        "cross_target_governance_boundaries.json": _governance_boundaries(),
    }

    written: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    for name, payload in artifacts.items():
        path = out / name
        _save_json(path, payload)
        written[name] = str(path.resolve())
        fingerprints[name] = _hash(payload)

    phase_summary = {
        "schema_version": "1.0",
        "phase": "PORTABLE_MULTI_TARGET_COGNITION",
        "reference_target": "RB3Gen2",
        "artifacts": written,
        "fingerprints": fingerprints,
        "constraints": {
            "advisory_or_governed_only": True,
            "fail_closed": True,
            "no_autonomous_patching": True,
            "no_autonomous_upstream_generation": True,
            "no_chat_memory_dependency": True,
        },
        "generated_at_epoch": time.time(),
    }

    summary_path = out / "portable_multi_target_cognition_phase_summary.json"
    _save_json(summary_path, phase_summary)

    print(
        json.dumps(
            {
                "summary": str(summary_path.resolve()),
                "artifacts": written,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
