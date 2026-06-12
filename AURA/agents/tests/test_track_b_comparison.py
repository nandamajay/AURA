"""Tests for Track-B comparison artifacts."""

from __future__ import annotations

from aura_agents.track_b_stage_execution import (
    _build_comparison_readiness_payload,
    _validate_comparison_matrix_schema,
)


def _comparison_matrix_payload() -> dict[str, object]:
    return {
        "artifact_name": "TRACK_B_COMPARISON_MATRIX",
        "schema_version": "1.0",
        "classification": "PASS",
        "platform": "sc7280",
        "corpora": [
            {
                "corpus_id": "audio-kernel-ar",
                "corpus_role": "downstream",
                "revision": {
                    "remote": "ssh://example/downstream",
                    "branch": "main",
                    "commit_sha": "a" * 40,
                },
            },
            {
                "corpus_id": "linux-next",
                "corpus_role": "upstream",
                "revision": {
                    "remote": "git://example/upstream",
                    "branch": "master",
                    "commit_sha": "b" * 40,
                },
            },
        ],
        "comparison_signals": {
            key: {
                "downstream_only": [],
                "upstream_only": [],
                "shared": ["shared-signal"],
                "downstream_count": 1,
                "upstream_count": 1,
                "shared_count": 1,
                "fingerprint": "f" * 64,
            }
            for key in (
                "symbols",
                "includes",
                "headers",
                "structs",
                "dependency_relationships",
                "dts_relationships",
                "yaml_relationships",
                "kconfig_relationships",
                "makefile_relationships",
            )
        },
        "lineage": {
            "discovered_artifact_sha256": "c" * 64,
            "indexed_artifact_sha256": "d" * 64,
            "static_artifact_sha256": "e" * 64,
        },
        "fail_closed_reasons": [],
    }


def test_comparison_matrix_schema_accepts_git_commit_sha():
    payload = _comparison_matrix_payload()
    assert _validate_comparison_matrix_schema(payload) == []


def test_comparison_matrix_schema_rejects_invalid_role():
    payload = _comparison_matrix_payload()
    payload["corpora"][0]["corpus_role"] = "invalid"
    errors = _validate_comparison_matrix_schema(payload)
    assert any("corpora roles must be exactly {downstream, upstream}" in error for error in errors)


def test_comparison_readiness_is_pass_when_signals_present():
    matrix = _comparison_matrix_payload()
    payload = _build_comparison_readiness_payload(
        comparison_matrix_payload=matrix,
        stage_confidence={"DISCOVERED": 1.0, "INDEXED": 1.0, "STATIC_ANALYZED": 1.0},
        stage_confidence_details={},
    )
    assert payload["classification"] == "PASS"
    assert payload["required_signals"]
    assert payload["missing_signals"] == []
