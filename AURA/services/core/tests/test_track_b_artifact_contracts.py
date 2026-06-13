"""Contract tests for Track-B artifact visibility and deterministic summaries."""

from __future__ import annotations

import json
from pathlib import Path

from core.contracts.track_b_artifact_contracts import (
    build_track_b_lineage,
    collect_track_b_artifacts,
    filter_track_b_artifacts,
    search_track_b,
    summarize_conflicts,
    summarize_dependency_coverage,
    summarize_equivalence,
    summarize_readiness,
    track_b_overview,
)

from track_b_test_fixtures import write_track_b_fixture


def test_collect_track_b_artifacts_is_deterministic(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)

    records_a, validation_a = collect_track_b_artifacts(repo_root=repo_root, strict=True)
    records_b, validation_b = collect_track_b_artifacts(repo_root=repo_root, strict=True)

    assert validation_a.valid is True
    assert validation_b.valid is True
    assert [record.metadata.artifact_id for record in records_a] == [
        record.metadata.artifact_id for record in records_b
    ]
    assert [record.metadata.artifact_file for record in records_a] == sorted(
        [record.metadata.artifact_file for record in records_a]
    )


def test_collect_track_b_artifacts_fail_closed_on_missing_required_field(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    run_root = write_track_b_fixture(repo_root)

    readiness_path = run_root / "track_b_upstreaming_readiness.json"
    payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    payload.pop("mandatory_checks")
    readiness_path.write_text(json.dumps(payload), encoding="utf-8")

    records, validation = collect_track_b_artifacts(repo_root=repo_root, strict=True)
    assert validation.valid is False
    assert any(issue.code == "missing_required_field" for issue in validation.issues)
    readiness = [
        record
        for record in records
        if record.metadata.artifact_file == "track_b_upstreaming_readiness.json"
    ][0]
    assert readiness.validation.valid is False


def test_lineage_and_summaries_are_evidence_backed(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    overview = track_b_overview(repo_root=repo_root, strict=True)
    records = overview["records"]

    lineage = build_track_b_lineage(records, component_query="q6apm_dai_prepare")
    assert lineage.validation.valid is True
    assert len(lineage.nodes) > 0
    assert len(lineage.edges) > 0

    readiness = summarize_readiness(records)
    conflicts = summarize_conflicts(records)
    deps = summarize_dependency_coverage(records)
    equivalence = summarize_equivalence(records)

    assert readiness["classification"] == "PASS"
    assert conflicts["classification"] == "PASS"
    assert deps["classification"] == "PASS"
    assert equivalence["classification"] == "PASS"


def test_filter_and_search_support_track_b_discovery(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    overview = track_b_overview(repo_root=repo_root, strict=True)

    filtered = filter_track_b_artifacts(
        overview["records"],
        artifact_name="UPSTREAMING_REPORT",
        decision_state="UNIQUE_EQUIVALENT",
        readiness_status="",
        component="q6apm_dai_prepare",
    )
    assert len(filtered) == 1
    assert filtered[0].metadata.artifact_file == "track_b_upstreaming_report.json"

    results = search_track_b(
        records=overview["records"],
        learning_records=overview["learning"],
        audits=overview["audits"],
        releases=overview["releases"],
        query="q6apm_dai_prepare",
        kind="artifact",
        limit=20,
    )
    assert len(results) >= 1
    assert all(result["kind"] == "artifact" for result in results)

    conflict_results = search_track_b(
        records=overview["records"],
        learning_records=overview["learning"],
        audits=overview["audits"],
        releases=overview["releases"],
        query="ORDERING_MISMATCH",
        kind="artifact",
        limit=20,
    )
    assert len(conflict_results) >= 1
