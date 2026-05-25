"""Static validation tests for runtime transport artifact contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.contracts.transport_artifact_contracts import (
    collect_runtime_artifacts,
    parse_runtime_artifact,
    runtime_environment_diagnostics,
    runtime_lineage_consistency,
)

FINGERPRINT = "a" * 64


def _base_payload(report_name: str) -> dict[str, object]:
    return {
        "report_name": report_name,
        "schema_version": "1.0.0",
        "target_id": "qcom-audio-target",
        "advisory_only_behavior": True,
        "runtime_truth_precedence": True,
        "classification": "PASS",
        "deterministic_fingerprint": FINGERPRINT,
        "evidence_references": ["trace://runtime/session-1"],
        "lineage_id": "lineage-1",
        "session_id": "session-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_execution_fingerprint": {
            "python_version": "3.12.2",
            "dependency_hashes": {
                "constraints_py312_sha256": FINGERPRINT,
                "pip_freeze_sha256": FINGERPRINT,
            },
            "git_sha": "0123456789abcdef0123456789abcdef01234567",
            "parser_version": "aura-runtime-parser-v1",
            "execution_container_hash": "sha256:runtime-container-hash",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def _write_runtime_artifacts(repo_root: Path) -> None:
    transport = repo_root / "docs" / "operations" / "transport"
    transport.mkdir(parents=True, exist_ok=True)

    runtime_equivalence = _base_payload("runtime_equivalence_report")
    runtime_equivalence.update(
        {
            "dimensions": [
                {
                    "dimension": "pcm_lifecycle",
                    "classification": "MATCHED",
                    "critical": True,
                    "difference_count": 0,
                    "drift_ratio": 0.0,
                    "baseline_count": 3,
                    "transformed_count": 3,
                    "weight": 0.4,
                }
            ],
            "summary": {
                "confidence_score": 0.96,
                "critical_divergence_count": 0,
                "total_differences": 0,
            },
        }
    )
    (transport / "runtime_equivalence_report.json").write_text(
        json.dumps(runtime_equivalence), encoding="utf-8"
    )

    hardware_truth = _base_payload("hardware_truth_graph")
    hardware_truth.update(
        {
            "nodes": {
                "fe_be_links": [
                    {"timestamp_ms": 100.0, "message": "FE0 -> BE0"},
                    {"timestamp_ms": 120.0, "message": "BE0 started"},
                ]
            },
            "summary": {"status": "stable"},
            "fail_closed_reasons": [],
        }
    )
    (transport / "hardware_truth_graph.json").write_text(
        json.dumps(hardware_truth), encoding="utf-8"
    )

    replay_consistency = _base_payload("replay_consistency_report")
    replay_consistency.update(
        {
            "consistency": {
                "deterministic_event_ordering": True,
                "lineage_fingerprint": FINGERPRINT,
                "previous_lineage_fingerprint": FINGERPRINT,
                "replay_drift": False,
            },
            "reasons": [],
        }
    )
    (transport / "replay_consistency_report.json").write_text(
        json.dumps(replay_consistency), encoding="utf-8"
    )

    governance = _base_payload("runtime_governance_decision")
    governance.update(
        {
            "promotion_eligible": True,
            "runtime_promotion_gate": {
                "confidence_score": 0.91,
                "confidence_threshold": 0.8,
                "critical_divergence_count": 0,
                "deterministic_replay_ready": True,
                "runtime_sensitive_impact_count": 0,
            },
            "runtime_inputs": {
                "runtime_confidence_fingerprint": FINGERPRINT,
                "runtime_divergence_fingerprint": FINGERPRINT,
                "runtime_equivalence_fingerprint": FINGERPRINT,
                "runtime_replay_fingerprint": FINGERPRINT,
            },
            "fail_closed_reasons": [],
        }
    )
    (transport / "runtime_governance_decision.json").write_text(
        json.dumps(governance), encoding="utf-8"
    )

    confidence = _base_payload("transformation_confidence_report")
    confidence.update(
        {
            "runtime_confidence": 0.91,
            "drivers": {
                "approved_transformations": 2,
                "blocked_transformations": 0,
                "compile_classification": "PASS",
                "missing_include_count": 0,
                "runtime_sensitive_region_count": 0,
                "symbol_lineage_consistent": True,
            },
            "summary": {
                "confidence_delta_from_threshold": 0.11,
                "confidence_threshold": 0.8,
            },
        }
    )
    (transport / "transformation_confidence_report.json").write_text(
        json.dumps(confidence), encoding="utf-8"
    )


def test_collect_runtime_artifacts_strict_has_known_contracts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_runtime_artifacts(repo_root)
    parsed = collect_runtime_artifacts(repo_root=repo_root, strict=True)
    assert len(parsed) == 5
    assert all(item.metadata.exists for item in parsed)
    assert all(item.contract is not None for item in parsed)


def test_lineage_consistency_is_warning_only_for_current_transport_set(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_runtime_artifacts(repo_root)
    parsed = collect_runtime_artifacts(repo_root=repo_root, strict=True)
    lineage = runtime_lineage_consistency(parsed)
    assert lineage.valid is True
    assert all(issue.severity != "error" for issue in lineage.issues)


def test_parse_runtime_artifact_missing_file_fail_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    parsed = parse_runtime_artifact("runtime_equivalence_report", missing_path, strict=True)
    assert parsed.validation.valid is False
    assert parsed.contract is None
    assert any(issue.code == "artifact_not_found" for issue in parsed.validation.issues)


def test_parse_runtime_artifact_contract_mismatch_detection(tmp_path: Path) -> None:
    malformed = tmp_path / "runtime_equivalence_report.json"
    malformed.write_text(json.dumps({"schema_version": "1.0"}))
    parsed = parse_runtime_artifact("runtime_equivalence_report", malformed, strict=True)
    assert parsed.validation.valid is False
    assert parsed.contract is None
    assert any(issue.code == "contract_validation_error" for issue in parsed.validation.issues)


def test_parse_runtime_artifact_requires_runtime_execution_fingerprint(tmp_path: Path) -> None:
    artifact = tmp_path / "runtime_equivalence_report.json"
    payload = _base_payload("runtime_equivalence_report")
    payload.pop("runtime_execution_fingerprint")
    payload.update(
        {
            "dimensions": [],
            "summary": {
                "confidence_score": 0.0,
                "critical_divergence_count": 0,
                "total_differences": 0,
            },
        }
    )
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    parsed = parse_runtime_artifact("runtime_equivalence_report", artifact, strict=True)
    assert parsed.validation.valid is False
    assert any(issue.code == "contract_validation_error" for issue in parsed.validation.issues)


def test_runtime_environment_diagnostics_fail_closed_when_transport_missing(tmp_path: Path) -> None:
    status = runtime_environment_diagnostics(
        repo_root=tmp_path,
        sqlite_path=str(tmp_path / "missing.db"),
    )
    assert status.classification == "FAIL_CLOSED"
    assert "transport_artifact_root_missing" in status.fail_closed_reasons
    assert "runtime_evidence_root_missing" in status.fail_closed_reasons
    assert "replay_store_unavailable" in status.fail_closed_reasons


def test_runtime_lineage_consistency_fails_on_execution_container_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_runtime_artifacts(repo_root)
    transport = repo_root / "docs" / "operations" / "transport"

    governance_path = transport / "runtime_governance_decision.json"
    governance_payload = json.loads(governance_path.read_text(encoding="utf-8"))
    governance_payload["runtime_execution_fingerprint"]["execution_container_hash"] = (
        "sha256:other-container"
    )
    governance_path.write_text(json.dumps(governance_payload), encoding="utf-8")

    parsed = collect_runtime_artifacts(repo_root=repo_root, strict=True)
    lineage = runtime_lineage_consistency(parsed)
    assert lineage.valid is False
    assert any(
        issue.code == "runtime_execution_container_hash_mismatch"
        for issue in lineage.issues
    )
