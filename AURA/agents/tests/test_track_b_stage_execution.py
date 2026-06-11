"""Tests for deterministic Track B stage execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aura_agents.track_b_stage_execution import TrackBStageExecutor


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

    indexed_payload = json.loads((output_dir / "track_b_indexed.json").read_text(encoding="utf-8"))
    assert indexed_payload["counts"]["driver_files"] >= 1
    assert indexed_payload["counts"]["dts_files"] >= 1
    assert indexed_payload["counts"]["yaml_files"] >= 1
    assert indexed_payload["counts"]["kconfig_files"] >= 1
    assert indexed_payload["counts"]["makefile_files"] >= 1

    static_payload = json.loads((output_dir / "track_b_static_analyzed.json").read_text(encoding="utf-8"))
    assert static_payload["driver_structure_map"]["nodes"]
    assert static_payload["symbol_relationship_map"]


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
