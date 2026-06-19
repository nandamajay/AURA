"""Tests for independent conversion verifier."""

from __future__ import annotations

import json
from pathlib import Path

from aura_agents.conversion_verifier import render_verification_json, verify_conversion


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_detects_byte_identical_copy(tmp_path: Path):
    converted = _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")
    reference = _write(tmp_path / "reference" / "driver.c", "static int f(void) { return 0; }\n")

    report = verify_conversion([converted.parent], reference_paths=[reference.parent])

    assert report["verdict"] == "FAIL"
    assert report["findings"]["blocking"][0]["byte_identical"] is True


def test_detects_renamed_reference_derivation(tmp_path: Path):
    reference_text = """
static int wcd938x_probe(void)
{
    return WCD938X_VALUE;
}
"""
    converted_text = reference_text.replace("wcd938x", "wcd937x").replace("WCD938X", "WCD937X")
    converted = _write(tmp_path / "converted" / "wcd937x.c", converted_text)
    reference = _write(tmp_path / "reference" / "wcd938x.c", reference_text)

    report = verify_conversion([converted.parent], reference_paths=[reference.parent], copy_threshold=99.0)

    assert report["verdict"] in {"WARN", "FAIL"}
    findings = report["findings"]["all_derivation_findings"]
    assert findings
    assert findings[0]["severity"] in {"DERIVATION_RISK", "COPY_RISK"}


def test_lineage_coverage_passes_when_functions_named(tmp_path: Path):
    converted = _write(
        tmp_path / "converted" / "driver.c",
        """
static int alpha_probe(void) { return 0; }
static int beta_remove(void) { return 0; }
""",
    )
    lineage = _write(
        tmp_path / "lineage.json",
        json.dumps({"functions": [{"name": "alpha_probe"}, {"name": "beta_remove"}]}),
    )

    report = verify_conversion([converted.parent], lineage_file=lineage)

    assert report["lineage_check"]["status"] == "CHECKED"
    assert report["lineage_check"]["coverage"] == 100.0
    assert report["verdict"] == "PASS"


def test_lineage_coverage_fails_when_missing(tmp_path: Path):
    converted = _write(
        tmp_path / "converted" / "driver.c",
        """
static int alpha_probe(void) { return 0; }
static int beta_remove(void) { return 0; }
""",
    )
    lineage = _write(tmp_path / "lineage.json", json.dumps({"functions": [{"name": "alpha_probe"}]}))

    report = verify_conversion([converted.parent], lineage_file=lineage, lineage_threshold=80.0)

    assert report["verdict"] == "FAIL"
    assert report["lineage_check"]["coverage"] == 50.0
    assert "beta_remove" in report["lineage_check"]["uncovered_functions"]


def test_no_lineage_warns_but_does_not_fail(tmp_path: Path):
    converted = _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")

    report = verify_conversion([converted.parent])

    assert report["verdict"] == "WARN"
    assert report["lineage_check"]["status"] == "SKIPPED"


def test_downstream_reuse_warns_not_blocks(tmp_path: Path):
    converted = _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")
    downstream = _write(tmp_path / "downstream" / "driver.c", "static int f(void) { return 0; }\n")
    lineage = _write(tmp_path / "lineage.json", json.dumps({"functions": ["f"]}))

    report = verify_conversion([converted.parent], downstream_paths=[downstream.parent], lineage_file=lineage)

    assert report["verdict"] == "WARN"
    assert report["findings"]["blocking"] == []
    assert report["findings"]["warnings"][0]["severity"] == "DOWNSTREAM_REUSE_RISK"


def test_render_is_deterministic(tmp_path: Path):
    converted = _write(tmp_path / "converted" / "driver.c", "static int f(void) { return 0; }\n")

    first = render_verification_json(verify_conversion([converted.parent]))
    second = render_verification_json(verify_conversion([converted.parent]))

    assert first == second
    assert json.loads(first) == json.loads(second)
