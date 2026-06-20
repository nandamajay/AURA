"""Focused tests for wcd_rule_pack_checker prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aura_agents.wcd_rule_pack_checker import _summarize
from aura_agents.wcd_rule_pack_checker import run_checker


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _rules_file(tmp_path: Path, runtime_required: bool = True, include_required_fields: bool = True) -> Path:
    rule_entry = {
        "rule_id": "WCD-FAMILY-PROMOTED-TEST-001",
        "rule": "Runtime-sensitive test rule",
        "enforcement": "gate",
        "runtime_evidence_required": runtime_required,
    }
    if not include_required_fields:
        rule_entry.pop("runtime_evidence_required")

    payload = {
        "artifact": "test_rules",
        "generated_on": "2026-06-20",
        "rules": [rule_entry],
    }
    return _write(tmp_path / "rules.json", json.dumps(payload, indent=2))


def _minimal_run_dir(tmp_path: Path, with_fail_closed: bool = True) -> Path:
    run_dir = tmp_path / "run"
    _write(run_dir / "allowed_sources.json", json.dumps({"allowed_sources": ["x"], "forbidden_until_scoring": []}))
    _write(run_dir / "governance_gate" / "governance_verdict.json", json.dumps({"verdict": "PASS", "verifier_summary": {"warning_count": 0}}))
    _write(run_dir / "patch_lineage.json", json.dumps({"per_function_lineage": [{"output_function": "foo"}]}))
    if with_fail_closed:
        _write(
            run_dir / "runtime_fail_closed_items.json",
            json.dumps({"items": [{"item": "x", "status": "FAIL_CLOSED"}]}, indent=2),
        )
    return run_dir


def _args(tmp_path: Path, rules: Path, run_dir: Path, output_name: str = "report.json") -> argparse.Namespace:
    return argparse.Namespace(
        rules=str(rules),
        run_dir=str(run_dir),
        output=str(tmp_path / output_name),
        strict=False,
        driver_family="wcd",
        terminology=["LA=downstream", "LE=upstream"],
    )


def test_report_schema_has_required_top_level_fields(tmp_path: Path):
    rules = _rules_file(tmp_path)
    run_dir = _minimal_run_dir(tmp_path)

    report = run_checker(_args(tmp_path, rules, run_dir))

    required = {
        "artifact",
        "generated_at_utc",
        "checker_version",
        "rules_path",
        "run_dir",
        "driver_family",
        "summary",
        "checks",
        "rule_mapping",
        "limitations",
    }
    assert required.issubset(set(report.keys()))
    assert report["artifact"] == "wcd_rule_pack_compliance_report"
    assert isinstance(report["checks"], list)


def test_missing_run_directory_returns_fail(tmp_path: Path):
    rules = _rules_file(tmp_path)
    missing_run = tmp_path / "does_not_exist"

    report = run_checker(_args(tmp_path, rules, missing_run))

    assert report["summary"]["overall_verdict"] == "FAIL"
    check_ids = {item["check_id"] for item in report["checks"]}
    assert "CHECK_RUN_DIR_EXISTS" in check_ids


def test_rule_file_missing_required_field_fails_rule_parse(tmp_path: Path):
    rules = _rules_file(tmp_path, include_required_fields=False)
    run_dir = _minimal_run_dir(tmp_path)

    report = run_checker(_args(tmp_path, rules, run_dir))

    rule_check = next(item for item in report["checks"] if item["check_id"] == "CHECK_RULE_FILE_PARSE")
    assert rule_check["status"] == "FAIL"


def test_vendor_token_scan_warns_on_known_tokens(tmp_path: Path):
    rules = _rules_file(tmp_path)
    run_dir = _minimal_run_dir(tmp_path)
    _write(run_dir / "converted" / "codec.c", "int msm_audio(void) { return 0; }\n/* bolero */\n")

    report = run_checker(_args(tmp_path, rules, run_dir))
    vendor_check = next(item for item in report["checks"] if item["check_id"] == "CHECK_VENDOR_ELIMINATION_HEURISTIC")

    assert vendor_check["status"] == "WARN"
    details = json.loads(vendor_check["details"])
    assert details["token_counts"]["msm_"] > 0
    assert details["token_counts"]["bolero"] > 0


def test_overall_verdict_logic_prioritizes_fail_then_warn_then_pass():
    assert _summarize([{"status": "PASS"}, {"status": "FAIL"}])["overall_verdict"] == "FAIL"
    assert _summarize([{"status": "PASS"}, {"status": "WARN"}])["overall_verdict"] == "WARN"
    assert _summarize([{"status": "PASS"}, {"status": "INFO"}])["overall_verdict"] == "PASS"
    assert _summarize([])["overall_verdict"] == "UNKNOWN"


def test_runtime_fail_closed_detection_reports_fail_closed_ok(tmp_path: Path):
    rules = _rules_file(tmp_path, runtime_required=True)
    run_dir = _minimal_run_dir(tmp_path, with_fail_closed=True)

    report = run_checker(_args(tmp_path, rules, run_dir))
    runtime_check = next(item for item in report["checks"] if item["check_id"] == "CHECK_RUNTIME_SENSITIVE_RULE_EVIDENCE")

    assert runtime_check["status"] == "FAIL_CLOSED_OK"
