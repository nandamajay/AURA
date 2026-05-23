from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.real_patch_application_governed_build import (  # noqa: E402
    RealPatchApplicationGovernedBuildEngine,
    RealPatchApplicationGovernedBuildRegistry,
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
        "deterministic_replay_fingerprint": "real-patch-build-replay-fp",
    }


def _build_tree_with_patch(
    tmp_path: Path,
    *,
    source_rel: str,
    before_text: str,
    after_text: str,
    with_missing_include: bool = False,
) -> tuple[Path, Path]:
    root = tmp_path / "downstream"
    src = root / source_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(before_text, encoding="utf-8")

    if with_missing_include:
        src.write_text('#include "missing_local_header.h"\n' + before_text, encoding="utf-8")
        after_text = '#include "missing_local_header.h"\n' + after_text

    import difflib

    diff = list(
        difflib.unified_diff(
            src.read_text(encoding="utf-8").splitlines(),
            after_text.splitlines(),
            fromfile=f"a/{source_rel}",
            tofile=f"b/{source_rel}",
            lineterm="",
        )
    )
    patch_text = "# test patch\n\n" + "\n".join(diff) + "\n"
    patch = tmp_path / "change.patch"
    patch.write_text(patch_text, encoding="utf-8")
    return root, patch


def test_real_patch_apply_and_incremental_compile_pass(tmp_path: Path) -> None:
    before = "\n".join(
        [
            "struct device;",
            "void vendor_dbg(struct device *dev, const char *fmt, ...);",
            "void dev_dbg(struct device *dev, const char *fmt, ...);",
            "int test_probe(struct device *dev)",
            "{",
            '    vendor_dbg(dev, "probe");',
            "    return 0;",
            "}",
            "",
        ]
    )
    after = before.replace("vendor_dbg(dev, \"probe\");", "dev_dbg(dev, \"probe\");")
    root, patch = _build_tree_with_patch(
        tmp_path,
        source_rel="asoc/test_probe.c",
        before_text=before,
        after_text=after,
    )
    engine = RealPatchApplicationGovernedBuildEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-build-session-a",
        lineage_id="real-build-lineage-a",
        evidence_references=["test://real_patch_build/pass"],
    ).build_bundle

    assert bundle["classification"] == "PASS"
    summary = bundle["artifacts"]["real_patch_validation_summary"]["summary"]
    assert summary["real_patch_applied_successfully"] is True
    assert summary["real_incremental_compile_succeeded"] is True
    assert summary["rollback_triggered"] is False


def test_fail_closed_when_include_and_compile_fail(tmp_path: Path) -> None:
    before = "\n".join(
        [
            "struct device;",
            "void vendor_dbg(struct device *dev, const char *fmt, ...);",
            "void dev_dbg(struct device *dev, const char *fmt, ...);",
            "int test_probe(struct device *dev)",
            "{",
            '    vendor_dbg(dev, "probe");',
            "    return 0;",
            "}",
            "",
        ]
    )
    after = before.replace("vendor_dbg(dev, \"probe\");", "dev_dbg(dev, \"probe\");")
    root, patch = _build_tree_with_patch(
        tmp_path,
        source_rel="asoc/test_probe.c",
        before_text=before,
        after_text=after,
        with_missing_include=True,
    )
    engine = RealPatchApplicationGovernedBuildEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-build-session-b",
        lineage_id="real-build-lineage-b",
        evidence_references=["test://real_patch_build/fail_compile"],
    ).build_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "dependency_closure_unresolved" in reasons
    assert "incremental_compile_failed" in reasons
    rollback = bundle["artifacts"]["rollback_lineage"]
    assert rollback["rollback_triggered"] is True
    assert rollback["rollback_status"] == "completed"


def test_fail_closed_when_runtime_sensitive_unsafe_touch(tmp_path: Path) -> None:
    before = "\n".join(
        [
            "int vendor_helper(int x);",
            "int upstream_helper(int x);",
            "int dsp_irq_handler(int v)",
            "{",
            "    return vendor_helper(v);",
            "}",
            "",
        ]
    )
    after = before.replace("vendor_helper(v)", "upstream_helper(v)")
    root, patch = _build_tree_with_patch(
        tmp_path,
        source_rel="dsp/irq_route.c",
        before_text=before,
        after_text=after,
    )
    engine = RealPatchApplicationGovernedBuildEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-build-session-c",
        lineage_id="real-build-lineage-c",
        evidence_references=["test://real_patch_build/runtime_sensitive"],
    ).build_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = set(bundle["fail_closed_reasons"])
    assert "runtime_sensitive_compile_regions_impacted_unsafely" in reasons
    assert bundle["artifacts"]["rollback_lineage"]["rollback_triggered"] is True


def test_persistence_and_replay(tmp_path: Path) -> None:
    before = "\n".join(
        [
            "struct device;",
            "void vendor_dbg(struct device *dev, const char *fmt, ...);",
            "void dev_dbg(struct device *dev, const char *fmt, ...);",
            "int test_probe(struct device *dev)",
            "{",
            '    vendor_dbg(dev, "probe");',
            "    return 0;",
            "}",
            "",
        ]
    )
    after = before.replace("vendor_dbg(dev, \"probe\");", "dev_dbg(dev, \"probe\");")
    root, patch = _build_tree_with_patch(
        tmp_path,
        source_rel="asoc/test_probe.c",
        before_text=before,
        after_text=after,
    )
    engine = RealPatchApplicationGovernedBuildEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        source_root=root,
        patch_path=patch,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        session_id="real-build-session-d",
        lineage_id="real-build-lineage-d",
        evidence_references=["test://real_patch_build/persist"],
    ).build_bundle

    registry_path = tmp_path / "registry.json"
    output_dir = tmp_path / "out"
    store = RealPatchApplicationGovernedBuildRegistry(
        cognition_registry_path=registry_path,
        output_dir=output_dir,
    )
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id="real-build-lineage-d")

    assert persisted["lineage_id"] == "real-build-lineage-d"
    assert replay["lineage_id"] == "real-build-lineage-d"
    assert (output_dir / "applied_patch.diff").exists()
    assert (output_dir / "real_patch_validation_summary.json").exists()

