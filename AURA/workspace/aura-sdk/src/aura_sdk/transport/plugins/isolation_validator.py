"""Plugin isolation validator for portable runtime hardening."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


class PluginIsolationValidator:
    """Static validator for plugin-runtime portability boundaries."""

    def __init__(self, repo_root: str | Path):
        self._root = Path(repo_root)

    def _core_files(self) -> list[Path]:
        base = self._root / "AURA/workspace/aura-sdk/src/aura_sdk/transport"
        return [
            base / "portable_runtime_layer.py",
            base / "semantic_cognition.py",
            base / "semantic_runtime_advisory.py",
            base / "cognition_correlation.py",
            base / "upstream_conversion_planner.py",
            base / "real_downstream_conversion_planner.py",
            base / "kernel_structural_cognition.py",
            base / "plugins/loader.py",
            base / "plugins/contracts.py",
        ]

    def _branching_findings(self, text: str) -> list[str]:
        patterns = (
            r"if\s+[^\n]*target[^\n]*==[^\n]*['\"](?:rb3|rb3gen2|qcs6490|qcm6490)['\"]",
            r"if\s+[^\n]*['\"](?:rb3|rb3gen2|qcs6490|qcm6490)['\"][^\n]*==[^\n]*target",
            r"match\s+target",
            r"case\s+['\"](?:rb3|rb3gen2|qcs6490|qcm6490)['\"]",
        )
        findings: list[str] = []
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                findings.append(pattern)
        return findings

    def _hidden_assumption_findings(self, text: str) -> list[str]:
        patterns = (
            "rb3",
            "rb3gen2",
            "qcs6490",
            "qcm6490",
            "wcd937x",
            "spkrleft",
            "wsa rx0 mux",
        )
        lowered = text.lower()
        return [marker for marker in patterns if marker in lowered]

    def validate(self) -> dict[str, Any]:
        files = self._core_files()
        portable_runtime_file = files[0]
        semantic_core_file = files[1]
        semantic_runtime_advisory_file = files[2]
        correlation_core_file = files[3]
        translation_core_file = files[4]
        real_ingestion_core_file = files[5]
        structural_core_file = files[6]
        loader_file = files[7]
        contract_file = files[8]
        branch_findings: dict[str, list[str]] = {}
        assumption_findings: dict[str, list[str]] = {}

        for path in files:
            text = _read(path)
            if not text:
                branch_findings[str(path)] = ["file_unreadable_or_missing"]
                assumption_findings[str(path)] = ["file_unreadable_or_missing"]
                continue

            branching = self._branching_findings(text)
            if branching:
                branch_findings[str(path)] = branching

            assumptions = self._hidden_assumption_findings(text)
            if assumptions:
                assumption_findings[str(path)] = assumptions

        portable_boundary_checks = {
            "portable_runtime_uses_plugin_loader": "TargetPluginLoader" in _read(portable_runtime_file),
            "portable_runtime_uses_negotiation_request": "PluginNegotiationRequest" in _read(portable_runtime_file),
            "semantic_core_uses_plugin_loader": "TargetPluginLoader" in _read(semantic_core_file),
            "semantic_core_invokes_plugin_adapters": all(
                token in _read(semantic_core_file)
                for token in (
                    ".dts_adapter(",
                    ".topology_adapter(",
                    ".vendor_api_adapter(",
                    ".subsystem_descriptor_provider(",
                )
            ),
            "semantic_runtime_advisory_invokes_plugin_semantic_adapter": ".semantic_knowledge_adapter(" in _read(
                semantic_runtime_advisory_file
            ),
            "correlation_core_uses_plugin_loader": "TargetPluginLoader" in _read(correlation_core_file),
            "correlation_core_invokes_plugin_evidence_adapters": all(
                token in _read(correlation_core_file)
                for token in (
                    ".runtime_evidence_adapter(",
                    ".topology_evidence_adapter(",
                    ".semantic_evidence_adapter(",
                )
            ),
            "translation_core_uses_plugin_loader": "TargetPluginLoader" in _read(translation_core_file),
            "translation_core_invokes_plugin_conversion_adapters": all(
                token in _read(translation_core_file)
                for token in (
                    ".downstream_upstream_adapter(",
                    ".topology_translation_adapter(",
                    ".runtime_conversion_adapter(",
                )
            ),
            "real_ingestion_core_uses_plugin_loader": "TargetPluginLoader" in _read(real_ingestion_core_file),
            "real_ingestion_core_invokes_plugin_ingestion_adapters": all(
                token in _read(real_ingestion_core_file)
                for token in (
                    ".downstream_ingestion_adapter(",
                    ".upstream_match_adapter(",
                    ".topology_reconstruction_adapter(",
                )
            ),
            "structural_core_uses_plugin_loader": "TargetPluginLoader" in _read(structural_core_file),
            "structural_core_invokes_plugin_structural_adapter": ".structural_cognition_adapter(" in _read(
                structural_core_file
            ),
            "loader_uses_contract_validation": "assert_plugin_contract" in _read(loader_file),
            "contract_has_required_providers": all(
                token in _read(contract_file)
                for token in (
                    "topology_provider",
                    "mixer_provider",
                    "pcm_provider",
                    "route_provider",
                    "evidence_provider",
                    "capability_provider",
                    "validation_provider",
                    "dts_adapter",
                    "topology_adapter",
                    "vendor_api_adapter",
                    "subsystem_descriptor_provider",
                    "runtime_evidence_adapter",
                    "topology_evidence_adapter",
                    "semantic_evidence_adapter",
                    "downstream_upstream_adapter",
                    "topology_translation_adapter",
                    "runtime_conversion_adapter",
                    "downstream_ingestion_adapter",
                    "upstream_match_adapter",
                    "topology_reconstruction_adapter",
                    "semantic_knowledge_adapter",
                    "structural_cognition_adapter",
                )
            ),
        }

        no_target_specific_branching = not branch_findings
        no_hidden_rb3_assumptions_in_core = not assumption_findings
        boundaries_ok = all(portable_boundary_checks.values())

        classification = "PASS"
        if not no_target_specific_branching or not boundaries_ok:
            classification = "FAIL_CLOSED"
        elif not no_hidden_rb3_assumptions_in_core:
            classification = "ADVISORY_ONLY"

        return {
            "schema_version": "1.0",
            "validator": "plugin_isolation_validator",
            "classification": classification,
            "no_target_specific_branching": no_target_specific_branching,
            "no_hidden_rb3_assumptions_in_core": no_hidden_rb3_assumptions_in_core,
            "portable_orchestration_boundaries_ok": boundaries_ok,
            "branching_findings": branch_findings,
            "hidden_assumption_findings": assumption_findings,
            "portable_boundary_checks": portable_boundary_checks,
            "core_files_scanned": [str(path) for path in files],
        }
