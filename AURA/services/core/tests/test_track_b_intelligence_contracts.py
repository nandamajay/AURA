"""Contract tests for Track-B M10 intelligence layer."""

from __future__ import annotations

from pathlib import Path

from core.contracts.track_b_intelligence_contracts import (
    build_cross_release_trends,
    build_executive_dashboard,
    build_learning_intelligence,
    build_readiness_forecast,
    build_recommendations,
    mine_patterns,
    track_b_intelligence_overview,
)
from core.contracts.track_b_artifact_contracts import track_b_overview

from track_b_test_fixtures import write_track_b_fixture


def test_track_b_intelligence_aggregates_are_deterministic(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    overview = track_b_overview(repo_root=repo_root, strict=True)
    records = overview["records"]

    trends = build_cross_release_trends(records)
    patterns = mine_patterns(records)
    recs = build_recommendations(records)
    learning = build_learning_intelligence(records)
    executive = build_executive_dashboard(records)
    forecast = build_readiness_forecast(records)

    trends_repeat = build_cross_release_trends(records)
    patterns_repeat = mine_patterns(records)
    recs_repeat = build_recommendations(records)
    learning_repeat = build_learning_intelligence(records)
    executive_repeat = build_executive_dashboard(records)
    forecast_repeat = build_readiness_forecast(records)

    assert trends["classification"] == "PASS"
    assert patterns["classification"] == "PASS"
    assert recs["classification"] == "PASS"
    assert learning["classification"] == "PASS"
    assert executive["classification"] == "PASS"
    assert forecast["classification"] == "PASS"

    assert len(trends["audit_trend"]) >= 1
    assert len(trends["release_trend"]) >= 1

    assert "recurring_failures" in patterns
    assert "recommendations" in recs
    assert "clusters" in learning
    assert "learning_trend" in trends
    assert "ranked_lessons" in learning
    assert "usefulness_model" in learning

    assert trends == trends_repeat
    assert patterns == patterns_repeat
    assert recs == recs_repeat
    assert learning == learning_repeat
    assert executive == executive_repeat
    assert forecast == forecast_repeat


def test_track_b_intelligence_overview_contains_all_sections(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)

    payload = track_b_intelligence_overview(strict=True)
    assert "trends" in payload
    assert "patterns" in payload
    assert "recommendations" in payload
    assert "learning" in payload
    assert "executive" in payload
    assert "forecast" in payload


def test_track_b_recommendations_include_evidence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    overview = track_b_overview(repo_root=repo_root, strict=True)
    payload = build_recommendations(overview["records"])
    for rec in payload.get("recommendations", []):
        assert rec.get("evidence_refs")
        assert rec.get("lineage_refs")
        assert rec.get("supporting_artifacts")
