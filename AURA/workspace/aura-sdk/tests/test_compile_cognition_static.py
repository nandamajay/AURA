from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.compile_cognition_engine import (  # noqa: E402
    CompileCognitionEngine,
    CompileCognitionRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


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
        "deterministic_replay_fingerprint": "compile-cognition-replay-fp",
    }


def _build_tree(
    tmp_path: Path,
    *,
    missing_include: bool = False,
    bad_kconfig_chain: bool = False,
    add_dsp: bool = False,
) -> Path:
    root = tmp_path / "downstream"
    (root / "asoc").mkdir(parents=True, exist_ok=True)
    (root / "include").mkdir(parents=True, exist_ok=True)

    (root / "asoc/test.h").write_text(
        "\n".join(
            [
                "#pragma once",
                "int helper_local(int x);",
                "",
            ]
        ),
        encoding="utf-8",
    )
    test_c = "\n".join(
        [
            '#include "test.h"',
            "int asoc_probe(int x)",
            "{",
            "    return helper_local(x);",
            "}",
            "",
        ]
    )
    if missing_include:
        test_c = '#include "missing_local.h"\n' + test_c
    (root / "asoc/test.c").write_text(test_c, encoding="utf-8")
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

    make_lines = ["obj-$(CONFIG_SND_TEST) += test.o helper.o"]
    if bad_kconfig_chain:
        make_lines.append("obj-$(CONFIG_SND_UNKNOWN_GUARD) += missing_link.o")
    (root / "asoc/Makefile").write_text("\n".join(make_lines) + "\n", encoding="utf-8")
    (root / "asoc/Kconfig").write_text(
        "\n".join(
            [
                "config SND_HELPER",
                '    bool "Helper"',
                "",
                "config SND_TEST",
                '    bool "Test"',
                "    depends on SND",
                "    select SND_HELPER",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if add_dsp:
        (root / "dsp").mkdir(parents=True, exist_ok=True)
        (root / "dsp/irq_path.c").write_text(
            "\n".join(
                [
                    "int dsp_irq_handler(int x)",
                    "{",
                    "    return x;",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return root


def _build_patch(root: Path, changes: dict[str, str]) -> Path:
    patch_lines: list[str] = ["# compile cognition patch", ""]
    for rel, after in sorted(changes.items()):
        before = (root / rel).read_text(encoding="utf-8")
        diff = difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        )
        patch_lines.extend(list(diff))
        patch_lines.append("")
    path = root.parent / "change.patch"
    path.write_text("\n".join(patch_lines).rstrip() + "\n", encoding="utf-8")
    return path


def test_compile_cognition_pass_on_closed_tree(tmp_path: Path) -> None:
    root = _build_tree(tmp_path)
    after = (root / "asoc/test.c").read_text(encoding="utf-8").replace("return helper_local(x);", "return helper_local(x);")
    patch = _build_patch(root, {"asoc/test.c": after})
    engine = CompileCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="compile-cognition-session-a",
        lineage_id="compile-cognition-lineage-a",
        evidence_references=["test://compile_cognition/pass"],
    ).compile_bundle

    assert bundle["classification"] == "PASS"
    assert bundle["fail_closed_reasons"] == []
    artifacts = bundle["artifacts"]
    assert artifacts["include_closure_graph"]["classification"] == "PASS"
    assert artifacts["symbol_dependency_graph"]["classification"] == "PASS"
    assert artifacts["kconfig_dependency_map"]["classification"] == "PASS"
    assert artifacts["subsystem_compile_topology"]["classification"] == "PASS"


def test_compile_cognition_fail_closed_on_missing_include(tmp_path: Path) -> None:
    root = _build_tree(tmp_path, missing_include=True)
    patch = _build_patch(root, {"asoc/test.c": (root / "asoc/test.c").read_text(encoding="utf-8")})
    engine = CompileCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="compile-cognition-session-b",
        lineage_id="compile-cognition-lineage-b",
        evidence_references=["test://compile_cognition/missing_include"],
    ).compile_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "include_closure_incomplete" in reasons
    assert "compile_confidence_below_threshold" in reasons


def test_compile_cognition_fail_closed_on_kconfig_makefile_inconsistency(tmp_path: Path) -> None:
    root = _build_tree(tmp_path, bad_kconfig_chain=True)
    patch = _build_patch(root, {"asoc/test.c": (root / "asoc/test.c").read_text(encoding="utf-8")})
    engine = CompileCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="compile-cognition-session-c",
        lineage_id="compile-cognition-lineage-c",
        evidence_references=["test://compile_cognition/kconfig"],
    ).compile_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "kconfig_dependency_chain_inconsistent" in reasons or "subsystem_compile_topology_unproven" in reasons


def test_compile_cognition_boundary_escalation_and_replay(tmp_path: Path) -> None:
    root = _build_tree(tmp_path, add_dsp=True)
    asoc_after = (root / "asoc/test.c").read_text(encoding="utf-8").replace(
        "return helper_local(x);", "return helper_local(x + 0);"
    )
    dsp_after = (root / "dsp/irq_path.c").read_text(encoding="utf-8").replace("return x;", "return x + 1;")
    patch = _build_patch(
        root,
        {
            "asoc/test.c": asoc_after,
            "dsp/irq_path.c": dsp_after,
        },
    )
    engine = CompileCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="compile-cognition-session-d",
        lineage_id="compile-cognition-lineage-d",
        evidence_references=["test://compile_cognition/boundary"],
    ).compile_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "compile_boundary_crossing_unsafe" in set(bundle["fail_closed_reasons"])

    registry_path = tmp_path / "registry.json"
    output_dir = tmp_path / "out"
    store = CompileCognitionRegistry(cognition_registry_path=registry_path, output_dir=output_dir)
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id="compile-cognition-lineage-d")
    assert persisted["lineage_id"] == "compile-cognition-lineage-d"
    assert replay["lineage_id"] == "compile-cognition-lineage-d"
    assert (output_dir / "compile_governance_escalation.json").exists()
    assert (output_dir / "deterministic_compile_replay.json").exists()
