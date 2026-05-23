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
            "portable_runtime_uses_plugin_loader": "TargetPluginLoader" in _read(files[0]),
            "portable_runtime_uses_negotiation_request": "PluginNegotiationRequest" in _read(files[0]),
            "loader_uses_contract_validation": "assert_plugin_contract" in _read(files[1]),
            "contract_has_required_providers": all(
                token in _read(files[2])
                for token in (
                    "topology_provider",
                    "mixer_provider",
                    "pcm_provider",
                    "route_provider",
                    "evidence_provider",
                    "capability_provider",
                    "validation_provider",
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
