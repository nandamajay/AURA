#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from hashlib import sha256
from pathlib import Path
from typing import Any

from aura_agents.equivalence_governance import (
    DependencyResolutionGovernanceGate,
    EquivalenceAssertionProposal,
    EquivalenceGovernanceGate,
    load_dependency_resolutions_from_artifact,
)
from aura_agents.stage_engine import canonical_json_sha256
from aura_agents.track_b_stage_execution import TrackBStageExecutor

REPO_ROOT = Path("/local/mnt/workspace/AURA_V1_upstream")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
KB_ARTIFACT = REPO_ROOT / "AURA_KB/drivers/lpass_va_macro/dependency_resolution_map.json"

STAGE_FILES = {
    "DISCOVERED": "track_b_discovered.json",
    "INDEXED": "track_b_indexed.json",
    "STATIC_ANALYZED": "track_b_static_analyzed.json",
    "EQUIVALENCE_MAPPED": "track_b_equivalence_map.json",
    "DEPENDENCIES_BOUND": "track_b_dependency_matrix.json",
    "CONFLICTS_EVALUATED": "track_b_conflict_ledger.json",
    "DECISION_FINALIZED": "track_b_equivalence_decision.json",
    "REPORT_GENERATED": "track_b_upstreaming_report.json",
    "READINESS_GATED": "track_b_upstreaming_readiness.json",
}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def control_plane() -> tuple[dict[str, str], dict[str, str]]:
    base = REPO_ROOT / "docs/operations/transport/tracks/upstream-learning"
    names = [
        "architecture_plan.md",
        "track_boundary_report.json",
        "learning_progress_model.json",
        "readiness_assessment.json",
    ]
    assets = {name: str(base / name) for name in names}
    hashes = {name: file_sha(base / name) for name in names}
    return assets, hashes


def evidence(signal_id: str, role: str, path: str, line: int, basis: str) -> dict[str, Any]:
    commit = "a" * 40 if role == "downstream" else "b" * 40
    corpus_id = "audio-kernel-ar" if role == "downstream" else "linux-next"
    return {
        "signal_id": signal_id,
        "score": 1.0,
        "extractor_id": f"diagnostic.{signal_id}.v1",
        "source_artifact_sha256": canonical_json_sha256({"signal_id": signal_id, "path": path, "basis": basis}),
        "evidence_type": f"governed_equivalence:{signal_id}",
        "corpus_role": role,
        "corpus_id": corpus_id,
        "remote": f"local:{corpus_id}",
        "branch": "diagnostic",
        "commit_sha": commit,
        "path": path,
        "source_path": path,
        "line_start": line,
        "line_end": line,
        "snippet_sha256": canonical_json_sha256({"path": path, "line": line, "basis": basis}),
        "source_artifact_name": "DIAGNOSTIC_GOVERNED_EQUIVALENCE_ASSERTION",
        "extraction_rule_id": f"diagnostic.{signal_id}.v1",
    }


def approved_equivalence_assertion() -> dict[str, Any]:
    proposal = EquivalenceAssertionProposal(
        assertion_type="governed_human_assertion",
        match_type="component_boundary_split",
        downstream_component={
            "component_type": "function",
            "symbol": "lpass_cdc_va_macro_probe",
            "component_name": "lpass_cdc_va_macro_probe",
            "source_path": "asoc/codecs/lpass-cdc/lpass-cdc-va-macro.c",
            "line_start": 2487,
            "line_end": 2487,
        },
        upstream_component={
            "component_type": "function",
            "symbol": "va_macro_probe",
            "component_name": "va_macro_probe",
            "source_path": "sound/soc/codecs/lpass-va-macro.c",
            "line_start": 1529,
            "line_end": 1529,
        },
        evidence=[
            evidence(
                "path_family",
                "downstream",
                "asoc/codecs/lpass-cdc/lpass-cdc-va-macro.c",
                2487,
                "lpass va macro downstream path family",
            ),
            evidence(
                "compatible_family",
                "upstream",
                "sound/soc/codecs/lpass-va-macro.c",
                1757,
                "qcom lpass va macro compatible family",
            ),
            evidence(
                "registration_role",
                "upstream",
                "sound/soc/codecs/lpass-va-macro.c",
                1529,
                "platform probe registration role",
            ),
        ],
    )
    approved = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="aura-pm-v1",
        rationale="component_boundary_split equivalence for diagnostic run",
        timestamp="2026-06-16T00:00:00Z",
    )
    return approved.to_dict()


def approved_dependency_resolutions() -> list[dict[str, Any]]:
    proposals = load_dependency_resolutions_from_artifact(KB_ARTIFACT)
    gate = DependencyResolutionGovernanceGate()
    approved = [
        gate.approve(
            proposal,
            approver_id="aura-pm-v1",
            rationale="engineering-analysis-verified-evidence-confidence>=0.88",
            timestamp="2026-06-16T00:00:00Z",
        ).to_dict()
        for proposal in proposals
    ]
    return approved


def build_context() -> dict[str, Any]:
    assets, hashes = control_plane()
    return {
        "task_id": "diagnostic-lpass-va-macro-governed-full",
        "platform": "lpass_va_macro",
        "workflow_kind": "track_b_discovery",
        "track_b_initial_stage": "DISCOVERED",
        "track_b_target_stage": "READINESS_GATED",
        "track_b_readiness": {
            "go_no_go": "GO_DISCOVERY_ONLY",
            "scope_mode": "DISCOVERY_ONLY",
            "hard_blockers": [],
        },
        "track_b_hard_blockers": [],
        "control_plane_assets": assets,
        "control_plane_sha256": hashes,
        "corpora": [
            {
                "corpus_id": "audio-kernel-ar",
                "corpus_role": "downstream",
                "repository_root": str(REPO_ROOT / "track_b_corpora/audio-kernel-ar"),
                "revision": {
                    "remote": "local:track_b_corpora/audio-kernel-ar",
                    "branch": "diagnostic",
                    "commit_sha": "a" * 40,
                },
                "source_roots": ["asoc/codecs/lpass-cdc", "include/asoc", "include/soc", "include/dsp"],
                "include_patterns": ["*.c", "*.h"],
                "exclude_patterns": [".git", ".git/*"],
            },
            {
                "corpus_id": "linux-next",
                "corpus_role": "upstream",
                "repository_root": str(REPO_ROOT / "track_b_corpora/linux-next"),
                "revision": {
                    "remote": "local:track_b_corpora/linux-next",
                    "branch": "diagnostic",
                    "commit_sha": "b" * 40,
                },
                "source_roots": ["sound/soc/codecs", "drivers/soundwire", "include/linux/soundwire"],
                "include_patterns": ["*.c", "*.h"],
                "exclude_patterns": [".git", ".git/*"],
            },
        ],
        "upstreaming_request": {
            "request_id": "req-lpass-va-macro-full-governed-diagnostic",
            "downstream_component": {
                "component_type": "function",
                "component_name": "lpass_cdc_va_macro_probe",
                "source_path": "asoc/codecs/lpass-cdc/lpass-cdc-va-macro.c",
                "line_start": 2487,
                "line_end": 2487,
            },
            "runtime_evidence_refs": ["runtime:engineering_analysis:diagnostic_placeholder"],
        },
        "governed_equivalence_assertions": [approved_equivalence_assertion()],
        "governed_dependency_resolutions": approved_dependency_resolutions(),
    }


def load_stage_payloads() -> dict[str, dict[str, Any]]:
    payloads = {}
    for stage, filename in STAGE_FILES.items():
        path = OUTPUT_DIR / filename
        if path.exists():
            try:
                payloads[stage] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                payloads[stage] = {"classification": "INVALID_JSON", "error": str(exc)}
    return payloads


def stage_classifications(payloads: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        stage: str(payloads.get(stage, {}).get("classification") or "NOT_RUN")
        for stage in STAGE_FILES
    }


def failed_checks(readiness: dict[str, Any]) -> dict[str, str]:
    checks = readiness.get("mandatory_checks") if isinstance(readiness, dict) else {}
    if not isinstance(checks, dict):
        return {}
    reasons = readiness.get("fail_closed_reasons") if isinstance(readiness, dict) else []
    reason_text = "; ".join(str(item) for item in reasons) if isinstance(reasons, list) else str(reasons)
    return {key: reason_text or "mandatory check false" for key, value in checks.items() if value is not True}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for child in OUTPUT_DIR.iterdir():
        if child.is_file():
            child.unlink()

    context = None
    execution = None
    error = None
    try:
        context = build_context()
        execution = TrackBStageExecutor(output_dir=OUTPUT_DIR).execute(context=context)
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc().splitlines(),
        }

    payloads = load_stage_payloads()
    readiness = payloads.get("READINESS_GATED", {})
    decision = payloads.get("DECISION_FINALIZED", {})
    selected_candidate = decision.get("selected_candidate") if isinstance(decision, dict) else {}
    result = {
        "diagnostic": "lpass_va_macro_track_b_full_governed_assertions",
        "runtime_evidence_refs_requested": ["engineering_analysis_only"],
        "runtime_evidence_placeholder_note": (
            "The current executor requires runtime evidence refs to match "
            "'<runtime|m7>:<type>:<id>'; this diagnostic preserves the requested placeholder exactly."
        ),
        "dependency_resolution_artifact": str(KB_ARTIFACT),
        "approved_dependency_resolution_count": len(context.get("governed_dependency_resolutions", [])) if context else 0,
        "approved_equivalence_assertion_count": len(context.get("governed_equivalence_assertions", [])) if context else 0,
        "execution_completed": execution is not None,
        "terminal_stage": execution.get("terminal_stage") if isinstance(execution, dict) else None,
        "stage_classifications": stage_classifications(payloads),
        "final_readiness_status": readiness.get("readiness_status") if readiness else "NOT_REACHED",
        "final_decision_state": decision.get("decision_state") if decision else "NOT_REACHED",
        "mandatory_checks": readiness.get("mandatory_checks", {}) if readiness else {},
        "remaining_fail_closed_reasons": readiness.get("fail_closed_reasons", []) if readiness else [],
        "failed_checks": failed_checks(readiness),
        "selected_candidate": selected_candidate if readiness.get("readiness_status") == "READY" else {},
        "not_ready_reason": None if readiness.get("readiness_status") == "READY" else "READINESS_GATED not reached or not ready",
        "error": error,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
