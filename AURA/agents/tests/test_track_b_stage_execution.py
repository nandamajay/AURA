"""Tests for deterministic Track B stage execution (M6 dual-corpus comparison)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aura_agents.track_b_stage_execution import CONFLICT_PRECEDENCE, CONFLICT_TYPES, TrackBStageExecutor, _build_static_analyzed


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_control_plane(tmp_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    root = tmp_path / "docs" / "operations" / "transport" / "tracks" / "upstream-learning"
    _write(root / "architecture_plan.md", "# plan\n")
    _write(root / "track_boundary_report.json", json.dumps({"artifact_name": "TRACK_BOUNDARY_REPORT"}))
    _write(root / "learning_progress_model.json", json.dumps({"artifact_name": "LEARNING_PROGRESS_MODEL"}))
    _write(
        root / "readiness_assessment.json",
        json.dumps(
            {
                "artifact_name": "TRACK_B_READINESS_ASSESSMENT",
                "go_no_go": "GO_DISCOVERY_ONLY",
                "scope_mode": "DISCOVERY_ONLY",
                "hard_blockers": [],
            }
        ),
    )
    assets = {
        "architecture_plan.md": str(root / "architecture_plan.md"),
        "track_boundary_report.json": str(root / "track_boundary_report.json"),
        "learning_progress_model.json": str(root / "learning_progress_model.json"),
        "readiness_assessment.json": str(root / "readiness_assessment.json"),
    }
    hashes = {name: _sha(Path(path)) for name, path in assets.items()}
    return assets, hashes


def _create_corpus(repo_root: Path, *, variant: str, duplicate_common_function: bool = False) -> None:
    _write(
        repo_root / "sound/soc/qcom/test_machine.c",
        (
            '#include "test_internal.h"\n'
            + (
                "static int downstream_probe(void) { return 0; }\n"
                if variant == "downstream"
                else "static int upstream_probe(void) { return 0; }\n"
            )
            + "int qcom_audio_common(void) { return 1; }\n"
        ),
    )
    _write(repo_root / "sound/soc/qcom/test_internal.h", "struct qcom_audio_ctx { int id; };\n")
    _write(
        repo_root / "arch/arm64/boot/dts/qcom/test-board.dts",
        "/dts-v1/;\n#include \"test-common.dtsi\"\n/ { model = \"Test\"; };\n",
    )
    _write(
        repo_root / "Documentation/devicetree/bindings/sound/test-audio.yaml",
        "title: Test Audio Binding\n$ref: /schemas/types.yaml#/definitions/string\n",
    )
    _write(
        repo_root / "sound/soc/qcom/Kconfig",
        "config SND_SOC_TEST\n\tbool \"Test\"\n\tdepends on ARCH_QCOM\n",
    )
    _write(repo_root / "sound/soc/qcom/Makefile", "obj-$(CONFIG_SND_SOC_TEST) += test_machine.o\n")
    if duplicate_common_function:
        _write(
            repo_root / "sound/soc/qcom/test_machine_extra.c",
            '#include "test_internal.h"\nint qcom_audio_common(void) { return 2; }\n',
        )


def _default_corpus_decl(
    *,
    corpus_id: str,
    role: str,
    repository_root: Path,
    commit_sha: str,
) -> dict[str, object]:
    return {
        "corpus_id": corpus_id,
        "corpus_role": role,
        "repository_root": str(repository_root),
        "revision": {
            "remote": f"ssh://example/{corpus_id}",
            "branch": "main",
            "commit_sha": commit_sha,
        },
        "source_roots": [
            "sound/soc/qcom",
            "arch/arm64/boot/dts/qcom",
            "Documentation/devicetree/bindings/sound",
        ],
        "include_patterns": [
            "*.c",
            "*.h",
            "*.dts",
            "*.dtsi",
            "*.yaml",
            "*.yml",
            "Kconfig",
            "Makefile",
            "*.mk",
        ],
        "exclude_patterns": [
            ".git",
            ".git/*",
        ],
    }


def _context(
    tmp_path: Path,
    *,
    target_stage: str = "STATIC_ANALYZED",
    upstreaming_request: dict[str, object] | None = None,
    duplicate_upstream_common: bool = False,
) -> dict[str, object]:
    downstream = tmp_path / "downstream"
    upstream = tmp_path / "upstream"
    _create_corpus(downstream, variant="downstream")
    _create_corpus(upstream, variant="upstream", duplicate_common_function=duplicate_upstream_common)
    assets, hashes = _create_control_plane(tmp_path)
    payload = {
        "task_id": "task-1",
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
            _default_corpus_decl(
                corpus_id="audio-kernel-ar",
                role="downstream",
                repository_root=downstream,
                commit_sha="a" * 40,
            ),
            _default_corpus_decl(
                corpus_id="linux-next",
                role="upstream",
                repository_root=upstream,
                commit_sha="b" * 40,
            ),
        ],
    }
    if upstreaming_request is not None:
        payload["upstreaming_request"] = upstreaming_request
    return payload


def _artifact_map(output_dir: Path) -> dict[str, str]:
    manifest = json.loads((output_dir / "track_b_artifact_manifest.json").read_text(encoding="utf-8"))
    return {item["name"]: item["sha256"] for item in manifest["artifacts"]}


def _upstreaming_request(
    *,
    request_id: str = "req-1",
    component_type: str = "function",
    component_name: str = "qcom_audio_common",
    runtime_evidence_refs: list[str] | None = None,
) -> dict[str, object]:
    refs = ["runtime:event:playback_start"] if runtime_evidence_refs is None else runtime_evidence_refs
    return {
        "request_id": request_id,
        "downstream_component": {
            "component_type": component_type,
            "component_name": component_name,
            "source_path": "sound/soc/qcom/test_machine.c",
            "line_start": 1,
            "line_end": 120,
        },
        "runtime_evidence_refs": refs,
    }


def test_track_b_stage_execution_success_path_with_comparison_artifacts(tmp_path):
    context = _context(tmp_path)
    output_dir = tmp_path / "out"

    result = TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    assert result["classification"] == "PASS"
    assert result["terminal_stage"] == "STATIC_ANALYZED"
    assert Path(result["comparison_matrix_artifact_path"]).name == "track_b_comparison_matrix.json"
    assert Path(result["comparison_readiness_artifact_path"]).name == "track_b_comparison_readiness.json"

    discovered_payload = json.loads((output_dir / "track_b_discovered.json").read_text(encoding="utf-8"))
    assert len(discovered_payload["corpora"]) == 2
    assert set(item["corpus_role"] for item in discovered_payload["corpora"]) == {"downstream", "upstream"}
    assert discovered_payload["discovery_inventory"]["downstream"]["all_files"]
    assert discovered_payload["discovery_inventory"]["upstream"]["all_files"]

    indexed_payload = json.loads((output_dir / "track_b_indexed.json").read_text(encoding="utf-8"))
    assert set(indexed_payload["corpus_indexes"].keys()) == {"downstream", "upstream"}
    assert set(indexed_payload["relationship_indexes"].keys()) == {
        "downstream_upstream_relationship_index",
        "dts_relationship_index",
        "yaml_relationship_index",
        "kconfig_relationship_index",
        "makefile_relationship_index",
    }

    static_payload = json.loads((output_dir / "track_b_static_analyzed.json").read_text(encoding="utf-8"))
    assert static_payload["comparison_signals"]["symbols"]["fingerprint"]
    assert static_payload["comparison_signals"]["includes"]["fingerprint"]
    assert static_payload["delta_fingerprints"]["symbols"]

    matrix_payload = json.loads((output_dir / "track_b_comparison_matrix.json").read_text(encoding="utf-8"))
    readiness_payload = json.loads((output_dir / "track_b_comparison_readiness.json").read_text(encoding="utf-8"))
    assert matrix_payload["classification"] == "PASS"
    assert len(matrix_payload["corpora"]) == 2
    assert readiness_payload["classification"] == "PASS"
    assert not readiness_payload["missing_signals"]

    artifact_names = set(_artifact_map(output_dir))
    assert {
        "TRACK_B_STAGE_DISCOVERED",
        "TRACK_B_STAGE_INDEXED",
        "TRACK_B_STAGE_STATIC_ANALYZED",
        "TRACK_B_COMPARISON_MATRIX",
        "TRACK_B_COMPARISON_READINESS",
        "TRACK_B_STAGE_EXECUTION",
    }.issubset(artifact_names)


def test_track_b_stage_execution_is_deterministic(tmp_path):
    context = _context(tmp_path)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    result_a = TrackBStageExecutor(output_dir=out_a).execute(context=dict(context))
    result_b = TrackBStageExecutor(output_dir=out_b).execute(context=dict(context))

    assert result_a["artifact_manifest"]["deterministic_bundle_hash"] == result_b["artifact_manifest"][
        "deterministic_bundle_hash"
    ]
    assert _artifact_map(out_a) == _artifact_map(out_b)

    exec_a = json.loads((out_a / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    exec_b = json.loads((out_b / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert exec_a["stage_confidence"] == exec_b["stage_confidence"]
    assert exec_a["stage_confidence_details"] == exec_b["stage_confidence_details"]


def test_track_b_discovered_enforces_include_and_exclude_patterns(tmp_path):
    context = _context(tmp_path)
    downstream_root = Path(context["corpora"][0]["repository_root"])
    _write(downstream_root / "sound/soc/qcom/ignored.txt", "ignore me\n")
    _write(downstream_root / "sound/soc/qcom/skip/hidden.c", "int hidden(void) { return 0; }\n")
    _write(downstream_root / "sound/soc/qcom/keep/visible.c", "int visible(void) { return 0; }\n")
    context["corpora"][0]["source_roots"] = ["sound/soc/qcom"]
    context["corpora"][0]["include_patterns"] = ["*.c", "*.h", "Kconfig", "Makefile"]
    context["corpora"][0]["exclude_patterns"] = ["skip", "skip/*", "*/skip/*", "*.txt"]
    context["track_b_target_stage"] = "DISCOVERED"

    output_dir = tmp_path / "out"
    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    discovered_payload = json.loads((output_dir / "track_b_discovered.json").read_text(encoding="utf-8"))
    all_files = discovered_payload["discovery_inventory"]["downstream"]["all_files"]
    assert "sound/soc/qcom/keep/visible.c" in all_files
    assert "sound/soc/qcom/ignored.txt" not in all_files
    assert "sound/soc/qcom/skip/hidden.c" not in all_files


def test_track_b_stage_execution_fail_closed_on_missing_provenance(tmp_path):
    context = _context(tmp_path)
    context["corpora"][0]["revision"].pop("remote", None)

    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("revision.remote" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_fail_closed_on_invalid_roles(tmp_path):
    context = _context(tmp_path)
    context["corpora"][0]["corpus_role"] = "invalid"

    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("corpus_role" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_fail_closed_on_malformed_corpora_metadata(tmp_path):
    context = _context(tmp_path)
    context["corpora"] = "invalid"

    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("corpora must be a list" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_fail_closed_on_invalid_confidence_input(tmp_path):
    context = _context(tmp_path)
    context["track_b_confidence_weights"] = {
        "DISCOVERED": {
            "corpus_roles_integrity": "not-a-number",
        }
    }
    output_dir = tmp_path / "out"

    with pytest.raises(RuntimeError, match="fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("track_b_confidence_weights" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_static_analyzed_consumes_indexed_payload_only():
    indexed_payload = {
        "artifact_name": "TRACK_B_STAGE_INDEXED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "INDEXED",
        "corpora": [
            {
                "corpus_id": "audio-kernel-ar",
                "corpus_role": "downstream",
                "repository_root": "/tmp/downstream",
                "revision": {"remote": "r1", "branch": "b1", "commit_sha": "a" * 40},
            },
            {
                "corpus_id": "linux-next",
                "corpus_role": "upstream",
                "repository_root": "/tmp/upstream",
                "revision": {"remote": "r2", "branch": "b2", "commit_sha": "b" * 40},
            },
        ],
        "corpus_indexes": {
            "downstream": {
                "analysis_inputs": {
                    "source_records": [
                        {
                            "source_path": "sound/soc/qcom/test_machine.c",
                            "include_directives": [{"included_header": "test_internal.h", "include_style": "quote"}],
                            "functions": ["downstream_probe", "qcom_audio_common"],
                            "structs": ["qcom_audio_ctx"],
                        }
                    ]
                }
            },
            "upstream": {
                "analysis_inputs": {
                    "source_records": [
                        {
                            "source_path": "sound/soc/qcom/test_machine.c",
                            "include_directives": [{"included_header": "test_internal.h", "include_style": "quote"}],
                            "functions": ["upstream_probe", "qcom_audio_common"],
                            "structs": ["qcom_audio_ctx"],
                        }
                    ]
                }
            },
        },
        "relationship_indexes": {
            "dts_relationship_index": {
                "records": [
                    {"corpus_role": "downstream", "records": [{"source_path": "a.dts"}]},
                    {"corpus_role": "upstream", "records": [{"source_path": "a.dts"}]},
                ]
            },
            "yaml_relationship_index": {
                "records": [
                    {"corpus_role": "downstream", "records": [{"source_path": "a.yaml"}]},
                    {"corpus_role": "upstream", "records": [{"source_path": "a.yaml"}]},
                ]
            },
            "kconfig_relationship_index": {
                "records": [
                    {"corpus_role": "downstream", "records": [{"source_path": "Kconfig"}]},
                    {"corpus_role": "upstream", "records": [{"source_path": "Kconfig"}]},
                ]
            },
            "makefile_relationship_index": {
                "records": [
                    {"corpus_role": "downstream", "records": [{"source_path": "Makefile"}]},
                    {"corpus_role": "upstream", "records": [{"source_path": "Makefile"}]},
                ]
            },
            "downstream_upstream_relationship_index": {
                "records": [],
            },
        },
        "discovered_artifact_sha256": "c" * 64,
    }

    payload = _build_static_analyzed(context={}, stage_payloads={"INDEXED": indexed_payload})
    assert payload["classification"] == "PASS"
    assert payload["stage_id"] == "STATIC_ANALYZED"
    assert payload["comparison_signals"]["symbols"]["downstream_count"] >= 1
    assert payload["comparison_signals"]["symbols"]["upstream_count"] >= 1
    assert payload["comparison_signals"]["symbols"]["fingerprint"]
    assert payload["delta_fingerprints"]["symbols"] == payload["comparison_signals"]["symbols"]["fingerprint"]


def test_track_b_stage_execution_m8_readiness_pass(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(),
    )
    output_dir = tmp_path / "out"
    result = TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    assert result["classification"] == "PASS"
    assert result["terminal_stage"] == "READINESS_GATED"
    readiness_payload = json.loads((output_dir / "track_b_upstreaming_readiness.json").read_text(encoding="utf-8"))
    assert readiness_payload["classification"] == "PASS"
    assert readiness_payload["readiness_status"] == "READY"

    decision_payload = json.loads((output_dir / "track_b_equivalence_decision.json").read_text(encoding="utf-8"))
    assert decision_payload["decision_state"] == "UNIQUE_EQUIVALENT"

    artifact_names = set(_artifact_map(output_dir))
    assert {
        "TRACK_B_EQUIVALENCE_MAP",
        "TRACK_B_DEPENDENCY_MATRIX",
        "TRACK_B_CONFLICT_LEDGER",
        "TRACK_B_EQUIVALENCE_DECISION",
        "TRACK_B_UPSTREAMING_REPORT",
        "TRACK_B_UPSTREAMING_READINESS",
    }.issubset(artifact_names)


def test_track_b_stage_execution_m8_fail_closed_on_missing_upstreaming_request(tmp_path):
    context = _context(tmp_path, target_stage="READINESS_GATED", upstreaming_request=None)
    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="upstreaming_request is required"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("upstreaming_request is required" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_m8_fail_closed_on_multi_equivalent(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(),
        duplicate_upstream_common=True,
    )
    output_dir = tmp_path / "out"

    with pytest.raises(RuntimeError, match="terminal stage READINESS_GATED fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    readiness_payload = json.loads((output_dir / "track_b_upstreaming_readiness.json").read_text(encoding="utf-8"))
    assert readiness_payload["classification"] == "FAIL_CLOSED"
    assert any("decision_state=MULTI_EQUIVALENT" in reason for reason in readiness_payload["fail_closed_reasons"])


def test_track_b_stage_execution_m8_fail_closed_on_runtime_sensitive_missing_runtime_evidence(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(
            component_type="apr_service",
            component_name="audio_prm_set_lpass_clk_cfg",
            runtime_evidence_refs=[],
        ),
    )
    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="runtime_evidence_refs must be non-empty for runtime-sensitive"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("runtime_evidence_refs must be non-empty for runtime-sensitive" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_m8_conflict_taxonomy_is_explicit(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(),
        duplicate_upstream_common=True,
    )
    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="terminal stage READINESS_GATED fail-closed"):
        TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    conflict_payload = json.loads((output_dir / "track_b_conflict_ledger.json").read_text(encoding="utf-8"))
    policy = conflict_payload["resolution_policy"]
    assert policy["supported_conflict_types"] == list(CONFLICT_TYPES)
    assert policy["conflict_precedence"] == list(CONFLICT_PRECEDENCE)
    for conflict in conflict_payload["conflicts"]:
        assert conflict["conflict_type"] in CONFLICT_TYPES


def test_track_b_stage_execution_m8_provenance_fields_complete(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(),
    )
    output_dir = tmp_path / "out"
    TrackBStageExecutor(output_dir=output_dir).execute(context=context)

    required = {
        "evidence_id",
        "evidence_type",
        "corpus_role",
        "corpus_id",
        "remote",
        "branch",
        "commit_sha",
        "path",
        "line_start",
        "line_end",
        "snippet_sha256",
        "source_artifact_name",
        "source_artifact_sha256",
        "extraction_rule_id",
    }

    eq_payload = json.loads((output_dir / "track_b_equivalence_map.json").read_text(encoding="utf-8"))
    prov_entries = [eq_payload["downstream_anchor"]["provenance"]]
    for candidate in eq_payload.get("candidate_mappings", []):
        prov_entries.extend(candidate.get("evidence", []))

    dep_payload = json.loads((output_dir / "track_b_dependency_matrix.json").read_text(encoding="utf-8"))
    for record in dep_payload.get("dependency_records", []):
        prov_entries.extend(record.get("provenance", []))

    assert prov_entries
    for entry in prov_entries:
        assert required.issubset(set(entry.keys()))
        assert isinstance(entry["line_start"], int) and entry["line_start"] >= 0
        assert isinstance(entry["line_end"], int) and entry["line_end"] >= entry["line_start"]
        assert len(entry["evidence_id"]) == 64
        assert len(entry["snippet_sha256"]) == 64
        assert len(entry["source_artifact_sha256"]) == 64


def test_track_b_stage_execution_m8_deterministic(tmp_path):
    context = _context(
        tmp_path,
        target_stage="READINESS_GATED",
        upstreaming_request=_upstreaming_request(),
    )
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    result_a = TrackBStageExecutor(output_dir=out_a).execute(context=dict(context))
    result_b = TrackBStageExecutor(output_dir=out_b).execute(context=dict(context))
    assert result_a["artifact_manifest"]["deterministic_bundle_hash"] == result_b["artifact_manifest"][
        "deterministic_bundle_hash"
    ]
    assert _artifact_map(out_a) == _artifact_map(out_b)
