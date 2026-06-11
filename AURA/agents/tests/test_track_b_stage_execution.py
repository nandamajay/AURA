"""Tests for deterministic Track B stage execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aura_agents.track_b_stage_execution import TrackBStageExecutor, _build_static_analyzed


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_control_plane(tmp_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    root = tmp_path / "docs" / "operations" / "transport" / "tracks" / "upstream-learning"
    _write(root / "architecture_plan.md", "# plan\n")
    _write(root / "track_boundary_report.json", json.dumps({"artifact_name": "TRACK_BOUNDARY_REPORT"}))
    _write(
        root / "learning_progress_model.json",
        json.dumps({"artifact_name": "LEARNING_PROGRESS_MODEL"}),
    )
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


def _create_minimal_source_tree(repo_root: Path) -> None:
    _write(
        repo_root / "sound/soc/qcom/test_machine.c",
        """
#include <linux/module.h>
#include "test_internal.h"
static int qcom_audio_probe(void) {
  return 0;
}
""".strip()
        + "\n",
    )
    _write(repo_root / "sound/soc/qcom/test_internal.h", "struct qcom_audio_ctx { int id; };\n")
    _write(
        repo_root / "arch/arm64/boot/dts/qcom/test-board.dts",
        "/dts-v1/;\n/ { model = \"Test\"; };\n",
    )
    _write(
        repo_root / "Documentation/devicetree/bindings/sound/test-audio.yaml",
        "title: Test Audio Binding\n",
    )
    _write(repo_root / "sound/soc/qcom/Kconfig", "config SND_SOC_TEST\n\tbool \"Test\"\n")
    _write(repo_root / "sound/soc/qcom/Makefile", "obj-$(CONFIG_SND_SOC_TEST) += test_machine.o\n")


def _context(tmp_path: Path) -> dict[str, object]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _create_minimal_source_tree(repo_root)
    assets, hashes = _create_control_plane(tmp_path)
    return {
        "task_id": "task-1",
        "platform": "sc7280",
        "workflow_kind": "track_b_discovery",
        "repository_root": str(repo_root),
        "source_roots": [
            "sound/soc/qcom",
            "arch/arm64/boot/dts/qcom",
            "Documentation/devicetree/bindings/sound",
        ],
        "track_b_initial_stage": "DISCOVERED",
        "track_b_target_stage": "STATIC_ANALYZED",
        "track_b_readiness": {
            "go_no_go": "GO_DISCOVERY_ONLY",
            "scope_mode": "DISCOVERY_ONLY",
            "hard_blockers": [],
        },
        "track_b_hard_blockers": [],
        "control_plane_assets": assets,
        "control_plane_sha256": hashes,
    }


def test_track_b_stage_execution_success_path(tmp_path):
    context = _context(tmp_path)
    output_dir = tmp_path / "out"
    executor = TrackBStageExecutor(output_dir=output_dir)
    result = executor.execute(context=context)

    assert result["classification"] == "PASS"
    assert result["initial_stage"] == "DISCOVERED"
    assert result["terminal_stage"] == "STATIC_ANALYZED"
    assert [item["to_stage"] for item in result["transitions"]] == ["INDEXED", "STATIC_ANALYZED"]

    execution_payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert execution_payload["classification"] == "PASS"
    assert execution_payload["terminal_stage"] == "STATIC_ANALYZED"

    discovered_payload = json.loads((output_dir / "track_b_discovered.json").read_text(encoding="utf-8"))
    inventory = discovered_payload["discovery_inventory"]
    assert inventory["all_files"]
    assert inventory["counts"]["all_files"] == len(inventory["all_files"])
    assert inventory["file_families"]["config_files"]

    indexed_payload = json.loads((output_dir / "track_b_indexed.json").read_text(encoding="utf-8"))
    assert indexed_payload["counts"]["driver_files"] >= 1
    assert indexed_payload["counts"]["dts_files"] >= 1
    assert indexed_payload["counts"]["yaml_files"] >= 1
    assert indexed_payload["counts"]["config_files"] >= 1
    assert indexed_payload["counts"]["makefile_files"] >= 1
    assert indexed_payload["analysis_inputs"]["source_records"]
    assert indexed_payload["analysis_inputs"]["counts"]["source_records"] == len(
        indexed_payload["analysis_inputs"]["source_records"]
    )
    assert indexed_payload["analysis_inputs"]["fingerprints"]["source_records"]

    static_payload = json.loads((output_dir / "track_b_static_analyzed.json").read_text(encoding="utf-8"))
    assert static_payload["driver_structure_map"]["nodes"]
    assert static_payload["symbol_relationship_map"]
    assert static_payload["symbol_inventory"]
    assert static_payload["function_inventory"]
    assert static_payload["include_relationships"]
    assert static_payload["source_header_relationships"]
    metadata = static_payload["dependency_graph_metadata"]
    assert metadata["node_count"] == len(static_payload["driver_structure_map"]["nodes"])
    assert metadata["edge_count"] == len(static_payload["driver_structure_map"]["edges"])
    assert metadata["graph_fingerprint"]
    assert metadata["indexed_input_fingerprint"]


def test_track_b_stage_execution_fail_closed_on_transition_order(tmp_path):
    context = _context(tmp_path)
    context["track_b_initial_stage"] = "STATIC_ANALYZED"
    context["track_b_target_stage"] = "INDEXED"
    output_dir = tmp_path / "out"
    executor = TrackBStageExecutor(output_dir=output_dir)

    with pytest.raises(RuntimeError, match="fail-closed"):
        executor.execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert payload["fail_closed_reasons"]


def test_track_b_stage_execution_fail_closed_on_control_plane_hash_mismatch(tmp_path):
    context = _context(tmp_path)
    context["control_plane_sha256"]["architecture_plan.md"] = "0" * 64
    output_dir = tmp_path / "out"
    executor = TrackBStageExecutor(output_dir=output_dir)

    with pytest.raises(RuntimeError, match="fail-closed"):
        executor.execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("sha256 mismatch" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_stage_execution_fail_closed_when_repository_root_missing(tmp_path):
    context = _context(tmp_path)
    context.pop("repository_root", None)
    output_dir = tmp_path / "out"
    executor = TrackBStageExecutor(output_dir=output_dir)

    with pytest.raises(RuntimeError, match="fail-closed"):
        executor.execute(context=context)

    payload = json.loads((output_dir / "track_b_stage_execution.json").read_text(encoding="utf-8"))
    assert payload["classification"] == "FAIL_CLOSED"
    assert any("repository_root is required" in reason for reason in payload["fail_closed_reasons"])


def test_track_b_discovered_enforces_include_and_exclude_patterns(tmp_path):
    context = _context(tmp_path)
    repo_root = Path(str(context["repository_root"]))
    _write(repo_root / "sound/soc/qcom/ignored.txt", "ignore me\n")
    _write(repo_root / "sound/soc/qcom/skip/hidden.c", "int hidden(void) { return 0; }\n")
    _write(repo_root / "sound/soc/qcom/keep/visible.c", "int visible(void) { return 0; }\n")

    context["source_roots"] = ["sound/soc/qcom"]
    context["include_patterns"] = ["*.c", "*.h", "Kconfig", "Makefile"]
    context["exclude_patterns"] = ["skip", "skip/*", "*/skip/*", "*.txt"]
    context["track_b_target_stage"] = "DISCOVERED"

    output_dir = tmp_path / "out"
    result = TrackBStageExecutor(output_dir=output_dir).execute(context=context)
    assert result["classification"] == "PASS"

    discovered_payload = json.loads((output_dir / "track_b_discovered.json").read_text(encoding="utf-8"))
    all_files = discovered_payload["discovery_inventory"]["all_files"]
    assert "sound/soc/qcom/keep/visible.c" in all_files
    assert "sound/soc/qcom/ignored.txt" not in all_files
    assert "sound/soc/qcom/skip/hidden.c" not in all_files


def test_track_b_discovered_uses_declared_source_roots_only(tmp_path):
    context = _context(tmp_path)
    repo_root = Path(str(context["repository_root"]))
    _write(repo_root / "unscoped/extra.c", "int extra(void) { return 0; }\n")
    context["source_roots"] = ["sound/soc/qcom"]
    context["include_patterns"] = ["*.c", "*.h", "Kconfig", "Makefile"]
    context["exclude_patterns"] = []
    context["track_b_target_stage"] = "DISCOVERED"

    output_dir = tmp_path / "out"
    TrackBStageExecutor(output_dir=output_dir).execute(context=context)
    discovered_payload = json.loads((output_dir / "track_b_discovered.json").read_text(encoding="utf-8"))
    all_files = discovered_payload["discovery_inventory"]["all_files"]
    assert "unscoped/extra.c" not in all_files


def test_track_b_stage_execution_is_deterministic(tmp_path):
    context = _context(tmp_path)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    result_a = TrackBStageExecutor(output_dir=out_a).execute(context=dict(context))
    result_b = TrackBStageExecutor(output_dir=out_b).execute(context=dict(context))

    assert result_a["artifact_manifest"]["deterministic_bundle_hash"] == result_b["artifact_manifest"][
        "deterministic_bundle_hash"
    ]

    a_manifest = json.loads((out_a / "track_b_artifact_manifest.json").read_text(encoding="utf-8"))
    b_manifest = json.loads((out_b / "track_b_artifact_manifest.json").read_text(encoding="utf-8"))
    a_map = {item["name"]: item["sha256"] for item in a_manifest["artifacts"]}
    b_map = {item["name"]: item["sha256"] for item in b_manifest["artifacts"]}
    assert a_map == b_map


def test_track_b_static_analyzed_consumes_indexed_payload_only():
    indexed_payload = {
        "artifact_name": "TRACK_B_STAGE_INDEXED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "INDEXED",
        "repository_root": "",
        "file_families": {
            "driver_files": [
                "sound/soc/qcom/test_machine.c",
                "sound/soc/qcom/test_internal.h",
            ],
            "dts_files": ["arch/arm64/boot/dts/qcom/test-board.dts"],
            "yaml_files": ["Documentation/devicetree/bindings/sound/test-audio.yaml"],
            "config_files": ["sound/soc/qcom/Kconfig"],
            "makefile_files": ["sound/soc/qcom/Makefile"],
        },
        "analysis_inputs": {
            "source_records": [
                {
                    "source_path": "sound/soc/qcom/test_machine.c",
                    "source_kind": "source",
                    "file_sha256": "a" * 64,
                    "line_count": 5,
                    "include_directives": [
                        {
                            "included_header": "test_internal.h",
                            "include_style": "quote",
                        }
                    ],
                    "functions": ["qcom_audio_probe"],
                    "structs": ["qcom_audio_ctx"],
                },
                {
                    "source_path": "sound/soc/qcom/test_internal.h",
                    "source_kind": "header",
                    "file_sha256": "b" * 64,
                    "line_count": 2,
                    "include_directives": [],
                    "functions": [],
                    "structs": ["qcom_audio_ctx"],
                },
            ],
            "counts": {},
            "fingerprints": {
                "source_records": "c" * 64,
            },
        },
    }

    payload = _build_static_analyzed(context={}, stage_payloads={"INDEXED": indexed_payload})
    assert payload["classification"] == "PASS"
    assert payload["stage_id"] == "STATIC_ANALYZED"
    assert payload["function_inventory"]
    assert payload["struct_inventory"]
    assert payload["include_relationships"]
    assert payload["source_header_relationships"]
