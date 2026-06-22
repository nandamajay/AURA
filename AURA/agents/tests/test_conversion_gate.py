"""Tests for conversion governance gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aura_agents.conversion_gate import run_gate
from aura_agents.conversion_gate import main as gate_main


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _args(tmp_path: Path, **overrides):
    defaults = {
        "run_dir": str(tmp_path / "run"),
        "allowed_sources": str(_write(tmp_path / "allowed_sources.json", json.dumps({"allowed_sources": ["downstream.c"]}))),
        "converted_dir": str(tmp_path / "converted"),
        "upstream_dir": None,
        "file_map": None,
        "reference": [],
        "target": [],
        "downstream": [],
        "lineage": None,
        "banned_symbols": None,
        "dt_binding": None,
        "reviewer_sim": False,
        "reviewer_sim_profiles_dir": None,
        "reviewer_sim_subsystem": "asoc",
        "derived_threshold": 85.0,
        "copy_threshold": 95.0,
        "lineage_threshold": 80.0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _minimal_profiles_dir(tmp_path: Path) -> Path:
    profiles_dir = tmp_path / "profiles"
    _write(
        profiles_dir / "krzysztof_kozlowski_profile_v4.json",
        json.dumps(
            {
                "reviewer": "Krzysztof Kozlowski",
                "confidence_level": "HIGH",
                "blocking_threshold": 3.0,
                "dt_rules": [],
            }
        ),
    )
    _write(
        profiles_dir / "mark_brown_profile_v4.json",
        json.dumps({"reviewer": "Mark Brown", "confidence_level": "HIGH"}),
    )
    _write(
        profiles_dir / "vinod_koul_profile_v4.json",
        json.dumps({"reviewer": "Vinod Koul", "confidence_level": "HIGH"}),
    )
    _write(
        profiles_dir / "pierre_louis_bossart_profile_v4.json",
        json.dumps({"reviewer": "Pierre-Louis Bossart", "confidence_level": "HIGH"}),
    )
    return profiles_dir


def test_gate_fails_on_reference_copy(tmp_path: Path):
    converted = _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")
    reference = _write(tmp_path / "reference" / "driver.c", "static int f(void) { return 0; }\n")

    result = run_gate(_args(tmp_path, reference=[str(reference.parent)]))

    assert result["verdict"] == "FAIL"
    assert "verifier_failed" in result["reasons"]
    assert Path(result["artifacts"]["verifier_result"]).exists()
    assert converted.exists()


def test_gate_passes_clean_lineage_only_run(tmp_path: Path):
    converted = _write(
        tmp_path / "converted" / "driver.c",
        "static int alpha_probe(void) { return 0; }\n",
    )
    lineage = _write(tmp_path / "lineage.json", json.dumps({"functions": ["alpha_probe"]}))

    result = run_gate(_args(tmp_path, lineage=str(lineage)))

    assert result["verdict"] == "WARN"
    assert "scoring_skipped_no_upstream_dir" in result["reasons"]
    assert result["verifier_summary"]["verdict"] == "PASS"
    assert Path(result["run_dir"], "governance_verdict.json").exists()
    assert converted.exists()


def test_gate_runs_multifile_scoring(tmp_path: Path):
    converted_source = """
#include <linux/module.h>
static int alpha_probe(void) { return 0; }
"""
    upstream_source = """
#include <linux/module.h>
#include <linux/platform_device.h>
static int alpha_probe(struct platform_device *pdev) { return 0; }
static int beta_remove(struct platform_device *pdev) { return 0; }
static int gamma_runtime_suspend(struct device *dev) { return 0; }
static int delta_runtime_resume(struct device *dev) { return 0; }
"""
    _write(tmp_path / "converted" / "driver.c", converted_source)
    _write(tmp_path / "upstream" / "driver.c", upstream_source)
    lineage = _write(tmp_path / "lineage.json", json.dumps({"functions": ["alpha_probe"]}))

    result = run_gate(_args(tmp_path, upstream_dir=str(tmp_path / "upstream"), lineage=str(lineage)))

    assert result["verdict"] == "PASS"
    assert result["score_summary"] is not None
    assert result["score_summary"]["paired_source_files"] == 1
    assert Path(result["artifacts"]["scoring_result"]).exists()


def test_gate_stages_target_files_for_scoring(tmp_path: Path):
    converted_source = """
#include <linux/module.h>
static int alpha_probe(void) { return 0; }
"""
    upstream_source = """
#include <linux/module.h>
#include <linux/platform_device.h>
static int alpha_probe(struct platform_device *pdev) { return 0; }
static int beta_remove(struct platform_device *pdev) { return 0; }
"""
    _write(tmp_path / "converted" / "driver.c", converted_source)
    upstream_file = _write(tmp_path / "target" / "driver.c", upstream_source)
    lineage = _write(tmp_path / "lineage.json", json.dumps({"functions": ["alpha_probe"]}))

    result = run_gate(_args(tmp_path, target=[str(upstream_file)], lineage=str(lineage)))

    assert result["score_summary"] is not None
    assert result["artifacts"]["staged_upstream_dir"] is not None
    assert Path(result["artifacts"]["staged_upstream_dir"], "driver.c").exists()


def test_gate_requires_allowed_sources(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")
    bad_allowed = _write(tmp_path / "bad_allowed.json", json.dumps({"allowed_sources": []}))

    try:
        run_gate(_args(tmp_path, allowed_sources=str(bad_allowed)))
    except RuntimeError as exc:
        assert "allowed_sources" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_cli_writes_fail_closed_verdict_on_setup_error(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")

    rc = gate_main([
        "--run-dir", str(tmp_path / "run"),
        "--allowed-sources", str(tmp_path / "missing_allowed.json"),
        "--converted-dir", str(tmp_path / "converted"),
    ])

    verdict = json.loads((tmp_path / "run" / "governance_verdict.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert verdict["verdict"] == "FAIL"
    assert "gate_error" in verdict["reasons"]


def test_gate_reviewer_sim_flag_adds_summary_field(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int alpha_probe(void) { return 0; }\n")
    profiles_dir = _minimal_profiles_dir(tmp_path)

    baseline = run_gate(_args(tmp_path, run_dir=str(tmp_path / "run_base")))
    result = run_gate(
        _args(
            tmp_path,
            run_dir=str(tmp_path / "run_with_sim"),
            reviewer_sim=True,
            reviewer_sim_profiles_dir=str(profiles_dir),
            reviewer_sim_subsystem="asoc",
        )
    )

    assert result["reviewer_sim_summary"] is not None
    assert result["reviewer_sim_summary"]["gate_impact"] == "NONE"
    assert result["reviewer_sim_summary"]["advisory_note"]
    assert result["verdict"] == baseline["verdict"]


def test_gate_without_reviewer_sim_has_null_summary(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int alpha_probe(void) { return 0; }\n")

    result = run_gate(_args(tmp_path, run_dir=str(tmp_path / "run_no_sim"), reviewer_sim=False))

    assert result["reviewer_sim_summary"] is None


def test_gate_reviewer_sim_never_changes_verdict(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int alpha_probe(void) { return 0; }\n")
    profiles_dir = _minimal_profiles_dir(tmp_path)

    without_sim = run_gate(_args(tmp_path, run_dir=str(tmp_path / "run_without_sim"), reviewer_sim=False))
    with_sim = run_gate(
        _args(
            tmp_path,
            run_dir=str(tmp_path / "run_with_sim"),
            reviewer_sim=True,
            reviewer_sim_profiles_dir=str(profiles_dir),
            reviewer_sim_subsystem="asoc",
        )
    )

    assert without_sim["verdict"] == with_sim["verdict"]


def test_gate_reviewer_sim_error_does_not_fail_gate(tmp_path: Path):
    _write(tmp_path / "converted" / "driver.c", "static int alpha_probe(void) { return 0; }\n")

    result = run_gate(
        _args(
            tmp_path,
            run_dir=str(tmp_path / "run_bad_sim"),
            reviewer_sim=True,
            reviewer_sim_profiles_dir=str(tmp_path / "missing_profiles"),
            reviewer_sim_subsystem="asoc",
        )
    )

    assert result["verdict"] in {"PASS", "WARN", "FAIL"}
    assert result["reviewer_sim_summary"] is not None
    assert result["reviewer_sim_summary"]["sim_verdict"] == "ERROR"
