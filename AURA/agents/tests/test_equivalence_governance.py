"""Tests for governed Track-B equivalence assertions."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from aura_agents.equivalence_governance import (
    DependencyResolutionAssertion,
    DependencyResolutionGovernanceGate,
    EquivalenceAssertionProposal,
    EquivalenceGovernanceGate,
    assertion_to_candidate_mapping,
    validate_assertion_proposal,
)
from aura_agents.track_b_stage_execution import TrackBStageExecutor


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _control_plane(tmp_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    from hashlib import sha256

    root = tmp_path / "docs" / "operations" / "transport" / "tracks" / "upstream-learning"
    files = {
        "architecture_plan.md": "# plan\n",
        "track_boundary_report.json": json.dumps({"artifact_name": "TRACK_BOUNDARY_REPORT"}),
        "learning_progress_model.json": json.dumps({"artifact_name": "LEARNING_PROGRESS_MODEL"}),
        "readiness_assessment.json": json.dumps(
            {
                "artifact_name": "TRACK_B_READINESS_ASSESSMENT",
                "go_no_go": "GO_DISCOVERY_ONLY",
                "scope_mode": "DISCOVERY_ONLY",
                "hard_blockers": [],
            }
        ),
    }
    assets: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name, content in files.items():
        path = root / name
        _write(path, content)
        assets[name] = str(path)
        hashes[name] = sha256(path.read_bytes()).hexdigest()
    return assets, hashes


def _base_proposal(
    *,
    evidence: list[dict[str, object]] | None = None,
    match_type: str = "governed_equivalence",
) -> EquivalenceAssertionProposal:
    return EquivalenceAssertionProposal(
        assertion_type="governed_human_assertion",
        match_type=match_type,
        downstream_component={
            "component_type": "function",
            "symbol": "lpass_cdc_va_macro_probe",
            "component_name": "lpass_cdc_va_macro_probe",
            "source_path": "sound/soc/qcom/lpass-cdc-va-macro.c",
            "line_start": 100,
            "line_end": 200,
        },
        upstream_component={
            "component_type": "function",
            "symbol": "va_macro_probe",
            "component_name": "va_macro_probe",
            "source_path": "sound/soc/codecs/lpass-va-macro.c",
            "line_start": 300,
            "line_end": 400,
        },
        evidence=[] if evidence is None else evidence,
    )


def _mandatory_evidence() -> list[dict[str, object]]:
    return [
        {
            "signal_id": "path_family",
            "score": 0.95,
            "extractor_id": "track_b.path_family.v1",
            "source_artifact_sha256": "a" * 64,
            "evidence_type": "governed_equivalence:path_family",
            "corpus_role": "downstream",
            "corpus_id": "audio-kernel-ar",
            "remote": "ssh://example/audio",
            "branch": "main",
            "commit_sha": "a" * 40,
            "path": "sound/soc/qcom/lpass-cdc-va-macro.c",
            "line_start": 1,
            "line_end": 1,
            "snippet_sha256": sha256(b"path_family").hexdigest(),
            "source_artifact_name": "TRACK_B_STAGE_INDEXED",
            "extraction_rule_id": "track_b.path_family.v1",
            "source_path": "sound/soc/qcom/lpass-cdc-va-macro.c",
        },
        {
            "signal_id": "compatible_family",
            "score": 0.9,
            "extractor_id": "track_b.compatible_family.v1",
            "source_artifact_sha256": "b" * 64,
            "evidence_type": "governed_equivalence:compatible_family",
            "corpus_role": "upstream",
            "corpus_id": "linux-next",
            "remote": "ssh://example/linux",
            "branch": "main",
            "commit_sha": "b" * 40,
            "path": "Documentation/devicetree/bindings/sound/qcom,lpass-va-macro.yaml",
            "line_start": 1,
            "line_end": 1,
            "snippet_sha256": sha256(b"compatible_family").hexdigest(),
            "source_artifact_name": "TRACK_B_STAGE_INDEXED",
            "extraction_rule_id": "track_b.compatible_family.v1",
            "source_path": "Documentation/devicetree/bindings/sound/qcom,lpass-va-macro.yaml",
        },
        {
            "signal_id": "registration_role",
            "score": 0.85,
            "extractor_id": "track_b.registration_role.v1",
            "source_artifact_sha256": "c" * 64,
            "evidence_type": "governed_equivalence:registration_role",
            "corpus_role": "upstream",
            "corpus_id": "linux-next",
            "remote": "ssh://example/linux",
            "branch": "main",
            "commit_sha": "b" * 40,
            "path": "sound/soc/codecs/lpass-va-macro.c",
            "line_start": 1,
            "line_end": 1,
            "snippet_sha256": sha256(b"registration_role").hexdigest(),
            "source_artifact_name": "TRACK_B_STAGE_INDEXED",
            "extraction_rule_id": "track_b.registration_role.v1",
            "source_path": "sound/soc/codecs/lpass-va-macro.c",
        },
    ]


def test_assertion_proposal_validation_rejects_missing_evidence():
    proposal = _base_proposal(evidence=[])

    valid, reasons = validate_assertion_proposal(proposal)

    assert valid is False
    assert "no_evidence" in reasons


def test_assertion_proposal_validation_rejects_missing_mandatory_signal():
    proposal = _base_proposal(evidence=_mandatory_evidence()[1:])

    assert proposal.confidence["value"] == 0.0
    assert "mandatory_signal_missing:path_family" in proposal.fail_closed_reasons


def test_governance_gate_blocks_unapproved():
    proposal = _base_proposal(evidence=_mandatory_evidence())

    assert assertion_to_candidate_mapping(proposal) is None


def test_governance_gate_approve_produces_auditable_mapping():
    proposal = _base_proposal(evidence=_mandatory_evidence())
    approved = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="evidence packet reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )

    mapping = assertion_to_candidate_mapping(approved)

    assert mapping is not None
    assert mapping["match_type"] == "governed_equivalence"
    assert mapping["confidence"] > 0
    assert mapping["evidence_refs"]
    assert mapping["governance"]["audit_ledger_sha256"]


def _create_integration_context(
    tmp_path: Path,
    approved_assertion: EquivalenceAssertionProposal,
    *,
    target_stage: str = "EQUIVALENCE_MAPPED",
) -> dict[str, object]:
    downstream = tmp_path / "downstream"
    upstream = tmp_path / "upstream"
    _write(
        downstream / "sound/soc/qcom/lpass-cdc-va-macro.c",
        "static int lpass_cdc_va_macro_probe(void) { return 0; }\n",
    )
    _write(
        upstream / "sound/soc/codecs/lpass-va-macro.c",
        "static int va_macro_probe(void) { return 0; }\n",
    )
    assets, hashes = _control_plane(tmp_path)
    return {
        "task_id": "task-governed-equivalence",
        "platform": "sc7280",
        "workflow_kind": "track_b_discovery",
        "track_b_initial_stage": "DISCOVERED",
        "track_b_target_stage": target_stage,
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
                "repository_root": str(downstream),
                "revision": {"remote": "ssh://example/audio", "branch": "main", "commit_sha": "a" * 40},
                "source_roots": ["sound/soc/qcom"],
                "include_patterns": ["*.c"],
                "exclude_patterns": [".git", ".git/*"],
            },
            {
                "corpus_id": "linux-next",
                "corpus_role": "upstream",
                "repository_root": str(upstream),
                "revision": {"remote": "ssh://example/linux", "branch": "main", "commit_sha": "b" * 40},
                "source_roots": ["sound/soc/codecs"],
                "include_patterns": ["*.c"],
                "exclude_patterns": [".git", ".git/*"],
            },
        ],
        "upstreaming_request": {
            "request_id": "req-governed-equivalence",
            "downstream_component": {
                "component_type": "function",
                "component_name": "lpass_cdc_va_macro_probe",
                "source_path": "sound/soc/qcom/lpass-cdc-va-macro.c",
                "line_start": 1,
                "line_end": 1,
            },
            "runtime_evidence_refs": [],
        },
        "governed_equivalence_assertions": [approved_assertion.to_dict()],
    }


def test_approved_assertion_feeds_into_stage_engine(tmp_path):
    proposal = _base_proposal(evidence=_mandatory_evidence())
    approved = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="evidence packet reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )
    context = _create_integration_context(tmp_path, approved)
    output_dir = tmp_path / "out"

    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    eq_payload = json.loads((output_dir / "track_b_equivalence_map.json").read_text(encoding="utf-8"))
    candidate_mappings = eq_payload["candidate_mappings"]
    assert candidate_mappings
    mapping = next(candidate for candidate in candidate_mappings if candidate.get("match_type") == "governed_equivalence")
    assert mapping["evidence_refs"]
    assert mapping["evidence_refs"][0]["extractor_id"] == "track_b.path_family.v1"
    assert mapping["governance"]["audit_ledger_sha256"] == approved.governance["audit_ledger_sha256"]


def test_component_boundary_split_suppresses_signature_mismatch_conflict(tmp_path):
    proposal = _base_proposal(evidence=_mandatory_evidence(), match_type="component_boundary_split")
    approved = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="component boundary split reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )
    context = _create_integration_context(tmp_path, approved, target_stage="CONFLICTS_EVALUATED")
    output_dir = tmp_path / "out"

    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    conflict_payload = json.loads((output_dir / "track_b_conflict_ledger.json").read_text(encoding="utf-8"))
    unresolved = [item for item in conflict_payload["conflicts"] if item["status"] == "UNRESOLVED"]
    resolved = [item for item in conflict_payload["conflicts"] if item["status"] == "RESOLVED_BY_GOVERNANCE"]
    assert not any(item["conflict_type"] == "SIGNATURE_MISMATCH" for item in unresolved)
    assert any(item["conflict_type"] == "SIGNATURE_MISMATCH_SUPPRESSED" for item in resolved)
    assert conflict_payload["unresolved_conflict_count"] == 0
    assert conflict_payload["resolved_conflict_count"] == 1


def test_structural_equivalence_keeps_signature_mismatch_conflict(tmp_path):
    proposal = _base_proposal(evidence=_mandatory_evidence(), match_type="structural_equivalence")
    approved = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="structural equivalence reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )
    context = _create_integration_context(tmp_path, approved, target_stage="CONFLICTS_EVALUATED")
    output_dir = tmp_path / "out"

    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    conflict_payload = json.loads((output_dir / "track_b_conflict_ledger.json").read_text(encoding="utf-8"))
    unresolved = [item for item in conflict_payload["conflicts"] if item["status"] == "UNRESOLVED"]
    assert any(item["conflict_type"] == "SIGNATURE_MISMATCH" for item in unresolved)
    assert not any(item["conflict_type"] == "SIGNATURE_MISMATCH_SUPPRESSED" for item in conflict_payload["conflicts"])


def _dependency_resolution_evidence(header: str) -> list[dict[str, object]]:
    return [
        {
            "signal_id": "usage_evidence",
            "score": 1.0,
            "extractor_id": "test.dependency_resolution.v1",
            "source_artifact_sha256": sha256(f"artifact:{header}".encode()).hexdigest(),
            "source_path": f"include/{header}",
            "path": f"include/{header}",
        }
    ]


def _approved_dependency_resolution(header: str) -> DependencyResolutionAssertion:
    proposal = DependencyResolutionAssertion(
        assertion_type="governed_human_assertion",
        driver="lpass_va_macro",
        dependency_header=header,
        resolution_type="REMOVAL_REQUIRED",
        upstream_equivalent=None,
        conversion_strategy=f"remove downstream-only dependency {header}",
        complexity="trivial",
        evidence=_dependency_resolution_evidence(header),
    )
    return DependencyResolutionGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="dependency resolution evidence reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )


_VENDOR_HEADERS = [
    "asoc/msm-cdc-pinctrl.h",
    "dsp/digital-cdc-rsc-mgr.h",
    "lpass-cdc.h",
    "lpass-cdc-registers.h",
    "lpass-cdc-clk-rsc.h",
    "soc/swr-common.h",
    "soc/swr-wcd.h",
    "linux/version.h",
]


def _context_with_vendor_dependency_gaps(
    tmp_path: Path,
    approved_assertion: EquivalenceAssertionProposal,
    resolved_headers: list[str],
) -> dict[str, object]:
    context = _create_integration_context(tmp_path, approved_assertion, target_stage="READINESS_GATED")
    downstream_root = Path(context["corpora"][0]["repository_root"])
    source_path = downstream_root / "sound/soc/qcom/lpass-cdc-va-macro.c"
    include_block = "".join(
        f"#include <{header}>\n" if "/" in header else f"#include \"{header}\"\n"
        for header in _VENDOR_HEADERS
    )
    _write(source_path, include_block + "static int lpass_cdc_va_macro_probe(void) { return 0; }\n")
    context["governed_dependency_resolutions"] = [
        _approved_dependency_resolution(header).to_dict() for header in resolved_headers
    ]
    return context


def test_full_pipeline_reaches_ready_with_governed_resolutions(tmp_path):
    proposal = _base_proposal(evidence=_mandatory_evidence(), match_type="component_boundary_split")
    approved_equivalence = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="component boundary split reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )
    context = _context_with_vendor_dependency_gaps(tmp_path, approved_equivalence, list(_VENDOR_HEADERS))
    output_dir = tmp_path / "out"

    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    readiness = json.loads((output_dir / "track_b_upstreaming_readiness.json").read_text(encoding="utf-8"))
    decision = json.loads((output_dir / "track_b_equivalence_decision.json").read_text(encoding="utf-8"))
    conflict = json.loads((output_dir / "track_b_conflict_ledger.json").read_text(encoding="utf-8"))
    assert readiness["classification"] != "FAIL_CLOSED"
    assert decision["decision_state"] == "UNIQUE_EQUIVALENT"
    assert readiness["readiness_status"] == "READY"
    assert all(readiness["mandatory_checks"].values())
    assert conflict["unresolved_conflict_count"] == 0


def test_partial_dependency_resolution_stays_fail_closed(tmp_path):
    proposal = _base_proposal(evidence=_mandatory_evidence(), match_type="component_boundary_split")
    approved_equivalence = EquivalenceGovernanceGate().approve(
        proposal,
        approver_id="maintainer:test",
        rationale="component boundary split reviewed",
        timestamp="2026-06-15T00:00:00Z",
    )
    context = _context_with_vendor_dependency_gaps(tmp_path, approved_equivalence, list(_VENDOR_HEADERS[:-1]))
    output_dir = tmp_path / "out"

    with pytest.raises(RuntimeError, match="terminal stage READINESS_GATED fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    readiness = json.loads((output_dir / "track_b_upstreaming_readiness.json").read_text(encoding="utf-8"))
    conflict = json.loads((output_dir / "track_b_conflict_ledger.json").read_text(encoding="utf-8"))
    assert readiness["classification"] == "FAIL_CLOSED"
    assert conflict["unresolved_conflict_count"] >= 1

