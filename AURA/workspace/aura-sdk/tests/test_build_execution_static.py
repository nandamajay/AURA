from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.build_execution_engine import (  # noqa: E402
    BuildExecutionEngine,
    BuildExecutionRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    reg = tmp_path / "simulation_registry.json"
    _write_json(reg, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=reg)


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
        "deterministic_replay_fingerprint": "build-exec-static-replay-fp",
    }


def _write_tree(
    tmp_path: Path,
    *,
    broken_deps: bool = False,
    runtime_sensitive: bool = False,
) -> tuple[Path, Path]:
    root = tmp_path / "kernel"
    (root / "asoc").mkdir(parents=True, exist_ok=True)

    top_make = "\n".join(
        [
            "modules:",
            "\t@echo MODPOST modules",
            "%:",
            "\t@echo BUILD $@",
            "",
        ]
    )
    (root / "Makefile").write_text(top_make, encoding="utf-8")

    asoc_kconfig = "\n".join(
        [
            "config SND_HELPER",
            '    bool "helper"',
            "",
            "config SND_TEST",
            '    bool "test"',
            "    depends on SND",
            "    select SND_HELPER",
            "",
        ]
    )
    (root / "asoc/Kconfig").write_text(asoc_kconfig, encoding="utf-8")

    make_line = "obj-$(CONFIG_SND_TEST) += test.o helper.o"
    if broken_deps:
        make_line += " missing_src.o"
    (root / "asoc/Makefile").write_text(make_line + "\n", encoding="utf-8")

    test_c_lines = [
        '#include "test.h"',
        "int helper_local(int x);",
        "int asoc_probe(int x)",
        "{",
        "    return helper_local(x);",
        "}",
        "",
    ]
    if runtime_sensitive:
        test_c_lines.insert(0, "int dsp_irq_path(int x) { return x; }")
    (root / "asoc/test.c").write_text("\n".join(test_c_lines), encoding="utf-8")
    (root / "asoc/helper.c").write_text(
        "\n".join(
            [
                '#include "test.h"',
                "int helper_local(int x)",
                "{",
                "    return x + 1;",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "asoc/test.h").write_text("#pragma once\nint helper_local(int x);\n", encoding="utf-8")

    patch = tmp_path / "change.patch"
    patch.write_text(
        "\n".join(
            [
                "# static patch",
                "--- a/asoc/test.c",
                "+++ b/asoc/test.c",
                "@@ -3,4 +3,4 @@",
                " int asoc_probe(int x)",
                " {",
                "-    return helper_local(x);",
                "+    return helper_local(x + 0);",
                " }",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root, patch


def test_build_execution_static_pass(tmp_path: Path) -> None:
    root, patch = _write_tree(tmp_path, broken_deps=False, runtime_sensitive=False)
    engine = BuildExecutionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="build-exec-session-a",
        lineage_id="build-exec-lineage-a",
        evidence_references=["test://build_execution/pass"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).build_bundle

    assert bundle["classification"] == "PASS"
    art = bundle["artifacts"]
    assert art["build_topology_graph"]["classification"] == "PASS"
    assert art["symbol_closure_report"]["classification"] == "PASS"
    assert art["build_confidence_report"]["classification"] == "PASS"
    assert art["governance_build_decision"]["classification"] == "PASS"


def test_build_execution_fail_closed_on_dependency_break(tmp_path: Path) -> None:
    root, patch = _write_tree(tmp_path, broken_deps=True)
    engine = BuildExecutionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="build-exec-session-b",
        lineage_id="build-exec-lineage-b",
        evidence_references=["test://build_execution/deps"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).build_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "dependency_graph_inconsistent" in reasons
    assert "compile_confidence_below_threshold" in reasons


def test_build_execution_fail_closed_runtime_sensitive_and_incremental(tmp_path: Path) -> None:
    root, patch = _write_tree(tmp_path, runtime_sensitive=True)
    engine = BuildExecutionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="build-exec-session-c",
        lineage_id="build-exec-lineage-c",
        evidence_references=["test://build_execution/runtime"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/does_not_exist.o"],
    ).build_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "incremental_rebuild_unsafe" in reasons
    assert "runtime_sensitive_regions_unsafe" in reasons


def test_build_execution_replay_and_registry(tmp_path: Path) -> None:
    root, patch = _write_tree(tmp_path)
    engine = BuildExecutionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="build-exec-session-d",
        lineage_id="build-exec-lineage-d",
        evidence_references=["test://build_execution/replay"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).build_bundle

    registry_path = tmp_path / "registry.json"
    output_dir = tmp_path / "out"
    store = BuildExecutionRegistry(cognition_registry_path=registry_path, output_dir=output_dir)
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id="build-exec-lineage-d")
    assert persisted["lineage_id"] == "build-exec-lineage-d"
    assert replay["lineage_id"] == "build-exec-lineage-d"
    assert (output_dir / "deterministic_build_replay.json").exists()
    assert (output_dir / "governance_build_decision.json").exists()

