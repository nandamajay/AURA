"""Track-B fixture helpers for deterministic endpoint/contract tests."""

from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def write_track_b_fixture(repo_root: Path, *, include_schema_freeze: bool = True) -> Path:
    docs_root = repo_root / "docs" / "operations" / "transport" / "tracks" / "upstream-learning"
    docs_root.mkdir(parents=True, exist_ok=True)
    run_root = repo_root / "track_b_validation" / "m8_audit" / "real_corpus_with_paths" / "q6apm_dai_prepare" / "run_1"
    run_root.mkdir(parents=True, exist_ok=True)

    if include_schema_freeze:
        _write_json(
            docs_root / "m8_schema_freeze.json",
            {
                "artifact_name": "M8_SCHEMA_FREEZE",
                "schema_version": "1.0",
                "status": "FROZEN",
                "frozen_artifacts": [
                    {
                        "artifact_name": "TRACK_B_EQUIVALENCE_MAP",
                        "artifact_file": "track_b_equivalence_map.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "upstreaming_request",
                            "corpora",
                            "downstream_anchor",
                            "candidate_mappings",
                            "ranking_policy",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                    {
                        "artifact_name": "TRACK_B_DEPENDENCY_MATRIX",
                        "artifact_file": "track_b_dependency_matrix.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "dependency_records",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                    {
                        "artifact_name": "TRACK_B_CONFLICT_LEDGER",
                        "artifact_file": "track_b_conflict_ledger.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "conflicts",
                            "unresolved_conflict_count",
                            "resolved_conflict_count",
                            "resolution_policy",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                    {
                        "artifact_name": "TRACK_B_EQUIVALENCE_DECISION",
                        "artifact_file": "track_b_equivalence_decision.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "decision_state",
                            "selected_candidate",
                            "mandatory_checks",
                            "complexity",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                    {
                        "artifact_name": "TRACK_B_UPSTREAMING_REPORT",
                        "artifact_file": "track_b_upstreaming_report.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "downstream_component",
                            "decision_state",
                            "upstream_equivalents",
                            "required_patches",
                            "risk_assessment",
                            "dependency_summary",
                            "architectural_differences",
                            "caller_callee_chain",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                    {
                        "artifact_name": "TRACK_B_UPSTREAMING_READINESS",
                        "artifact_file": "track_b_upstreaming_readiness.json",
                        "required_fields": [
                            "artifact_name",
                            "schema_version",
                            "classification",
                            "stage_id",
                            "decision_state",
                            "readiness_status",
                            "mandatory_checks",
                            "lineage",
                            "evidence",
                            "fail_closed_reasons",
                        ],
                    },
                ],
            },
        )

    _write_json(
        docs_root / "m8_fresh_audit_report.json",
        {
            "artifact_name": "M8_FRESH_AUDIT_REPORT",
            "schema_version": "1.0",
            "classification": "PASS",
            "metrics": {
                "blocker_count": 0,
                "m8_completion_percentage": 100.0,
                "production_readiness_percentage": 95.0,
            },
            "targets": {"blockers_eq_0": True},
        },
    )

    evidence = [
        {
            "evidence_id": "ev-1",
            "evidence_type": "symbol_reference",
            "corpus_role": "upstream",
            "corpus_id": "linux-next",
            "path": "sound/soc/soc-core.c",
            "line_range": "101-118",
        }
    ]

    base_context = {
        "schema_version": "1.0",
        "classification": "PASS",
        "lineage": {
            "component_id": "cmp-q6apm_dai_prepare",
            "decision_id": "decision-q6apm_dai_prepare",
        },
        "evidence": evidence,
        "fail_closed_reasons": [],
        "platform": "sc7280",
        "task_id": "task-trackb-1",
    }

    _write_json(
        run_root / "track_b_equivalence_map.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_EQUIVALENCE_MAP",
            "stage_id": "EQUIVALENCE_MAPPED",
            "upstreaming_request": {
                "component_type": "function",
                "runtime_sensitive": False,
                "runtime_evidence_refs": [],
                "downstream_component": {
                    "component_name": "q6apm_dai_prepare",
                    "source_path": "techpack/audio/apm/q6apm-dai.c",
                    "line_start": 240,
                    "line_end": 330,
                },
            },
            "corpora": [
                {
                    "corpus_id": "audio-kernel-ar",
                    "corpus_role": "downstream",
                    "provenance": {
                        "remote": "ssh://review-android.quicinc.com/platform/vendor/qcom/opensource/audio-kernel-ar",
                        "branch": "audio-kernel-cmn.lnx.0.0",
                        "commit_sha": "1111111111111111111111111111111111111111",
                    },
                },
                {
                    "corpus_id": "linux-next",
                    "corpus_role": "upstream",
                    "provenance": {
                        "remote": "git://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git",
                        "branch": "master",
                        "commit_sha": "2222222222222222222222222222222222222222",
                    },
                },
            ],
            "downstream_anchor": {
                "component_name": "q6apm_dai_prepare",
                "source_path": "techpack/audio/apm/q6apm-dai.c",
                "line_start": 240,
                "line_end": 330,
            },
            "candidate_mappings": [
                {
                    "candidate_id": "cand-1",
                    "upstream_symbol": "q6apm_dai_prepare",
                    "upstream_path": "sound/soc/qcom/qdsp6/q6apm-dai.c",
                    "upstream_line_start": 102,
                    "mapping_score": 0.94,
                    "evidence": evidence,
                }
            ],
            "ranking_policy": {
                "order": [
                    "mapping_score_desc",
                    "upstream_symbol_asc",
                    "upstream_path_asc",
                    "upstream_line_start_asc",
                ]
            },
        },
    )

    _write_json(
        run_root / "track_b_dependency_matrix.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_DEPENDENCY_MATRIX",
            "stage_id": "DEPENDENCIES_BOUND",
            "dependency_records": [
                {
                    "candidate_id": "cand-1",
                    "upstream_path": "sound/soc/qcom/qdsp6/q6apm-dai.c",
                    "downstream_path": "techpack/audio/apm/q6apm-dai.c",
                    "missing_dependency_count": 0,
                    "mandatory_checks": {
                        "dts_resolved": True,
                        "kconfig_resolved": True,
                    },
                }
            ],
        },
    )

    _write_json(
        run_root / "track_b_conflict_ledger.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_CONFLICT_LEDGER",
            "stage_id": "CONFLICTS_EVALUATED",
            "conflicts": [
                {
                    "conflict_id": "cx-1",
                    "conflict_type": "ORDERING_MISMATCH",
                    "severity": "MEDIUM",
                    "status": "RESOLVED",
                    "summary": "ordering validated with runtime evidence",
                    "candidate_ids": ["cand-1"],
                    "provenance": evidence,
                }
            ],
            "unresolved_conflict_count": 0,
            "resolved_conflict_count": 1,
            "resolution_policy": {
                "unresolved_requires_fail_closed": True,
            },
        },
    )

    _write_json(
        run_root / "track_b_equivalence_decision.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_EQUIVALENCE_DECISION",
            "stage_id": "DECISION_FINALIZED",
            "decision_state": "UNIQUE_EQUIVALENT",
            "selected_candidate": {
                "candidate_id": "cand-1",
                "upstream_symbol": "q6apm_dai_prepare",
            },
            "mandatory_checks": {
                "provenance_complete": True,
                "dependencies_resolved": True,
                "conflicts_resolved": True,
            },
            "complexity": {"label": "MEDIUM", "score": 45},
        },
    )

    _write_json(
        run_root / "track_b_upstreaming_report.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_UPSTREAMING_REPORT",
            "stage_id": "REPORT_GENERATED",
            "downstream_component": {
                "component_name": "q6apm_dai_prepare",
                "component_type": "function",
                "source_path": "techpack/audio/apm/q6apm-dai.c",
                "line_start": 240,
                "line_end": 330,
            },
            "decision_state": "UNIQUE_EQUIVALENT",
            "upstream_equivalents": [
                {
                    "candidate_id": "cand-1",
                    "symbol": "q6apm_dai_prepare",
                    "path": "sound/soc/qcom/qdsp6/q6apm-dai.c",
                }
            ],
            "required_patches": [
                {
                    "category": "feature-parity",
                    "summary": "validate feature flags on SC7xx audio paths",
                }
            ],
            "risk_assessment": {
                "complexity_label": "MEDIUM",
                "risk_points": [],
                "unresolved_conflict_count": 0,
            },
            "dependency_summary": {"total": 1, "resolved": 1},
            "architectural_differences": [],
            "caller_callee_chain": [
                {
                    "stage": "ALSA",
                    "file": "sound/soc/qcom/qdsp6/q6apm-dai.c",
                    "function": "q6apm_dai_prepare",
                    "caller": "soc_pcm_prepare",
                    "callee": "q6apm_graph_prepare",
                    "purpose": "prepare stream graph",
                }
            ],
        },
    )

    _write_json(
        run_root / "track_b_upstreaming_readiness.json",
        {
            **base_context,
            "artifact_name": "TRACK_B_UPSTREAMING_READINESS",
            "stage_id": "READINESS_GATED",
            "decision_state": "UNIQUE_EQUIVALENT",
            "readiness_status": "READY",
            "mandatory_checks": {
                "decision_unique_equivalent": True,
                "dependencies_resolved": True,
                "conflicts_resolved": True,
                "provenance_complete": True,
                "report_complete": True,
            },
        },
    )

    return run_root

