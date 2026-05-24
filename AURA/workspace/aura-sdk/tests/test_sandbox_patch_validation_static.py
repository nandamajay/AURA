from __future__ import annotations

import difflib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.sandbox_patch_validation_engine import (  # noqa: E402
    SandboxPatchValidationEngine,
    SandboxPatchValidationRegistry,
)


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
        "deterministic_replay_fingerprint": "sandbox-patch-validation-replay-fp",
    }


def _build_tree(
    tmp_path: Path,
    *,
    failing_object_target: bool = False,
    modpost_failure: bool = False,
) -> tuple[Path, Path, str]:
    root = tmp_path / "kernel"
    (root / "asoc").mkdir(parents=True, exist_ok=True)

    top_make = [
        "modules:",
        "\t@echo modules ok",
    ]
    if modpost_failure:
        top_make.extend(
            [
                "asoc/test.o:",
                "\t@echo \"modpost: error: undefined symbol foo\"",
                "\t@false",
            ]
        )
    elif failing_object_target:
        top_make.extend(
            [
                "asoc/test.o:",
                "\t@echo \"incremental build fail\"",
                "\t@false",
            ]
        )
    else:
        top_make.extend(
            [
                "asoc/test.o:",
                "\t@echo \"building asoc/test.o\"",
                "\t@mkdir -p $(O)/asoc",
                "\t@touch $(O)/asoc/test.o",
            ]
        )
    top_make.extend(
        [
            "%:",
            "\t@echo BUILD $@",
            "",
        ]
    )
    (root / "Makefile").write_text("\n".join(top_make), encoding="utf-8")
    (root / "asoc/Makefile").write_text("obj-$(CONFIG_SND_TEST) += test.o helper.o\n", encoding="utf-8")
    (root / "asoc/Kconfig").write_text(
        "\n".join(
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
        ),
        encoding="utf-8",
    )
    (root / "asoc/test.h").write_text("#pragma once\nstruct device;\n", encoding="utf-8")
    before = "\n".join(
        [
            '#include "test.h"',
            "int helper_alias(int x);",
            "int qcom_probe(struct device *dev, int x)",
            "{",
            "    pr_debug(\"probe %d\", x);",
            "    return helper_alias(x);",
            "}",
            "",
        ]
    )
    after = before.replace("pr_debug", "dev_dbg")
    (root / "asoc/test.c").write_text(before, encoding="utf-8")
    (root / "asoc/helper.c").write_text(
        "\n".join(
            [
                '#include "test.h"',
                "int helper_alias(int x)",
                "{",
                "    return x + 1;",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    diff = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="a/asoc/test.c",
            tofile="b/asoc/test.c",
            lineterm="",
        )
    )
    patch_text = "# tiny patch\n\n" + "\n".join(diff) + "\n"
    patch_path = tmp_path / "change.patch"
    patch_path.write_text(patch_text, encoding="utf-8")

    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(root), check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=AURA Test",
            "-c",
            "user.email=aura-test@example.com",
            "commit",
            "-m",
            "init",
        ],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    )
    return root, patch_path, before


def test_sandbox_patch_validation_pass_and_isolation(tmp_path: Path) -> None:
    root, patch, before_text = _build_tree(tmp_path)
    engine = SandboxPatchValidationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_paths=[patch],
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="sandbox-session-a",
        lineage_id="sandbox-lineage-a",
        evidence_references=["test://sandbox_patch_validation/pass"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).validation_bundle

    assert bundle["classification"] == "PASS"
    art = bundle["artifacts"]
    assert art["runtime_promotion_eligibility"]["eligible"] is True
    assert art["rollback_lineage_report"]["rollback_triggered"] is False
    # Source tree remains unchanged
    assert (root / "asoc/test.c").read_text(encoding="utf-8") == before_text


def test_fail_closed_when_patch_conflicts(tmp_path: Path) -> None:
    root, patch, _ = _build_tree(tmp_path)
    patch.write_text(
        "\n".join(
            [
                "# conflicting patch",
                "--- a/asoc/test.c",
                "+++ b/asoc/test.c",
                "@@ -100,3 +100,3 @@",
                "-not_present();",
                "+still_not_present();",
                "",
            ]
        ),
        encoding="utf-8",
    )
    engine = SandboxPatchValidationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_paths=[patch],
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="sandbox-session-b",
        lineage_id="sandbox-lineage-b",
        evidence_references=["test://sandbox_patch_validation/conflict"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).validation_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "patch_application_partially_failed" in reasons


def test_fail_closed_on_incremental_failure_and_rollback(tmp_path: Path) -> None:
    root, patch, _ = _build_tree(tmp_path, failing_object_target=True)
    engine = SandboxPatchValidationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_paths=[patch],
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="sandbox-session-c",
        lineage_id="sandbox-lineage-c",
        evidence_references=["test://sandbox_patch_validation/incremental"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).validation_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "compile_integrity_uncertain" in reasons
    rollback = bundle["artifacts"]["rollback_lineage_report"]
    assert rollback["rollback_triggered"] is True
    assert rollback["classification"] == "PASS"


def test_fail_closed_on_modpost_linker_and_replay_persistence(tmp_path: Path) -> None:
    root, patch, _ = _build_tree(tmp_path, modpost_failure=True)
    engine = SandboxPatchValidationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_paths=[patch],
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="sandbox-session-d",
        lineage_id="sandbox-lineage-d",
        evidence_references=["test://sandbox_patch_validation/modpost"],
        subsystem_targets=["asoc"],
        object_targets=["asoc/test.o"],
    ).validation_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "modpost_integrity_failed" in reasons
    assert bundle["artifacts"]["runtime_promotion_eligibility"]["eligible"] is False

    registry_path = tmp_path / "registry.json"
    output_dir = tmp_path / "out"
    store = SandboxPatchValidationRegistry(
        cognition_registry_path=registry_path,
        output_dir=output_dir,
    )
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id="sandbox-lineage-d")
    assert persisted["lineage_id"] == "sandbox-lineage-d"
    assert replay["lineage_id"] == "sandbox-lineage-d"
    assert (output_dir / "deterministic_patch_validation_replay.json").exists()
    assert (output_dir / "governance_patch_validation_decision.json").exists()
