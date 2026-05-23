from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.real_source_tree_governed_conversion import (  # noqa: E402
    RealSourceTreeGovernedConversionEngine,
    RealSourceTreeGovernedConversionRegistry,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "real-source-tree-replay-fp",
    }


def _fixture_tree(tmp_path: Path, *, missing_include: bool = False, only_sensitive: bool = False) -> Path:
    root = tmp_path / "downstream"
    (root / "asoc").mkdir(parents=True, exist_ok=True)
    (root / "dsp").mkdir(parents=True, exist_ok=True)
    (root / "include/asoc").mkdir(parents=True, exist_ok=True)
    (root / "Kconfig").write_text("config SND_QCOM_TEST\n\tbool \"QCOM TEST\"\n", encoding="utf-8")
    (root / "Makefile").write_text("obj-y += asoc/\n", encoding="utf-8")
    (root / "include/asoc/msm_common.h").write_text("#pragma once\nint msm_helper(int x);\n", encoding="utf-8")
    if not only_sensitive:
        includes = '#include "asoc/msm_probe.h"\n'
        if missing_include:
            includes += '#include "asoc/missing_dep.h"\n'
        (root / "asoc/msm_probe.c").write_text(
            "\n".join(
                [
                    "#include <linux/platform_device.h>",
                    "#include <linux/device.h>",
                    includes.strip(),
                    "int msm_probe(struct platform_device *pdev)",
                    "{",
                    '    pr_debug("%s: probe\\n", __func__);',
                    "    return 0;",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (root / "asoc/msm_probe.h").write_text("#pragma once\nint msm_probe(struct platform_device *pdev);\n", encoding="utf-8")

    (root / "dsp/dsp_irq.c").write_text(
        "\n".join(
            [
                "#include <linux/irqreturn.h>",
                "int q6_mailbox_irq_handler(int irq, void *data)",
                "{",
                '    pr_debug("%s: irq\\n", __func__);',
                "    return 0;",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_real_source_tree_governed_conversion_generates_artifacts(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import real_source_tree_governed_conversion as module  # noqa: E402

    def _compile_ok(*, source_root: Path, changed_sources: dict[str, str]) -> dict:
        return {
            "compile_attempted": True,
            "classification": "PASS",
            "reason": "",
            "files_checked": len(changed_sources),
            "failed_files": [],
            "command": "cc -x c -std=gnu11 -fsyntax-only ...",
        }

    monkeypatch.setattr(module, "_compile_validation", _compile_ok)

    root = _fixture_tree(tmp_path, missing_include=False, only_sensitive=False)
    engine = RealSourceTreeGovernedConversionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-source-session-a",
        lineage_id="real-source-lineage-a",
        evidence_references=["test://real_source_tree/artifacts"],
    ).conversion_bundle

    artifacts = bundle["artifacts"]
    required = {
        "source_tree_graph",
        "subsystem_boundary_map",
        "symbol_dependency_graph",
        "wrapper_classification_report",
        "governed_conversion_plan",
        "compile_validation_report",
        "runtime_sensitive_regions",
        "governance_escalation_report",
        "deterministic_driver_replay",
        "transformation_confidence_report",
        "upstream_equivalence_map",
        "downstream_to_upstream_patch",
        "real_driver_conversion_summary",
    }
    assert required.issubset(set(artifacts.keys()))
    patch = artifacts["downstream_to_upstream_patch"]["patch_text"]
    assert "dev_dbg(&pdev->dev" in patch
    assert artifacts["downstream_to_upstream_patch"]["real_patch_generated"] is True


def test_fail_closed_when_only_runtime_sensitive_regions_available(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import real_source_tree_governed_conversion as module  # noqa: E402

    def _compile_ok(*, source_root: Path, changed_sources: dict[str, str]) -> dict:
        return {
            "compile_attempted": True,
            "classification": "PASS",
            "reason": "",
            "files_checked": len(changed_sources),
            "failed_files": [],
            "command": "cc -x c -std=gnu11 -fsyntax-only ...",
        }

    monkeypatch.setattr(module, "_compile_validation", _compile_ok)
    root = _fixture_tree(tmp_path, only_sensitive=True)
    engine = RealSourceTreeGovernedConversionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-source-session-b",
        lineage_id="real-source-lineage-b",
        evidence_references=["test://real_source_tree/sensitive"],
    ).conversion_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_escalation_report"]["escalation_reasons"]
    assert "no_safe_transformations_available" in reasons


def test_fail_closed_when_include_dependency_validation_fails(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import real_source_tree_governed_conversion as module  # noqa: E402

    def _compile_ok(*, source_root: Path, changed_sources: dict[str, str]) -> dict:
        return {
            "compile_attempted": True,
            "classification": "PASS",
            "reason": "",
            "files_checked": len(changed_sources),
            "failed_files": [],
            "command": "cc -x c -std=gnu11 -fsyntax-only ...",
        }

    monkeypatch.setattr(module, "_compile_validation", _compile_ok)
    root = _fixture_tree(tmp_path, missing_include=True)
    engine = RealSourceTreeGovernedConversionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-source-session-c",
        lineage_id="real-source-lineage-c",
        evidence_references=["test://real_source_tree/include"],
    ).conversion_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_escalation_report"]["escalation_reasons"]
    assert "dependency_graph_inconsistent" in reasons


def test_deterministic_replay_and_registry_persistence(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import real_source_tree_governed_conversion as module  # noqa: E402

    def _compile_ok(*, source_root: Path, changed_sources: dict[str, str]) -> dict:
        return {
            "compile_attempted": True,
            "classification": "PASS",
            "reason": "",
            "files_checked": len(changed_sources),
            "failed_files": [],
            "command": "cc -x c -std=gnu11 -fsyntax-only ...",
        }

    monkeypatch.setattr(module, "_compile_validation", _compile_ok)
    root = _fixture_tree(tmp_path, missing_include=False)
    engine = RealSourceTreeGovernedConversionEngine(_loader(tmp_path))
    kwargs = {
        "target_id": "fake_target_alpha",
        "source_root": root,
        "governance_state": _governance(),
        "replay_traces": _replay(),
        "plugin_capability_state": {"supported": True},
        "previous_history": [],
        "session_id": "real-source-session-d",
        "lineage_id": "real-source-lineage-d",
        "evidence_references": ["test://real_source_tree/replay"],
    }
    first = engine.analyze(**kwargs).conversion_bundle
    second = engine.analyze(**kwargs).conversion_bundle
    assert first["conversion_fingerprint"] == second["conversion_fingerprint"]
    assert (
        first["artifacts"]["deterministic_driver_replay"]["deterministic_fingerprint"]
        == second["artifacts"]["deterministic_driver_replay"]["deterministic_fingerprint"]
    )

    registry = RealSourceTreeGovernedConversionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="real-source-lineage-d")
    replay_two = registry.replay(lineage_id="real-source-lineage-d")
    assert persisted["lineage_id"] == "real-source-lineage-d"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

