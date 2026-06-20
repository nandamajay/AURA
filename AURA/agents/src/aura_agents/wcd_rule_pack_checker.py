"""Prototype WCD rule-pack compliance checker.

This module validates conversion/run artifact directories against promoted WCD
family governance rules. It is deterministic and report-only: it does not
modify canonical gate/scorer/verifier behavior and does not claim runtime
readiness.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHECKER_VERSION = "prototype-0.1"

REQUIRED_RULE_FIELDS = {
    "rule_id",
    "rule",
    "enforcement",
    "runtime_evidence_required",
}

VENDOR_TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("qcom,msm", re.compile(r"qcom,msm", re.IGNORECASE)),
    ("asoc_msm", re.compile(r"\basoc_msm\b", re.IGNORECASE)),
    ("msm_", re.compile(r"\bmsm_[A-Za-z0-9_]*", re.IGNORECASE)),
    ("bolero", re.compile(r"\bbolero\b", re.IGNORECASE)),
    ("wcd9xxx", re.compile(r"\bwcd9xxx\b", re.IGNORECASE)),
    ("CONFIG_SND_SOC_QDSP6V2", re.compile(r"\bCONFIG_SND_SOC_QDSP6V2\b")),
]

TARGET_HIDDEN_PATTERNS = (
    re.compile(r"wcd939x\.c$"),
    re.compile(r"wcd939x-sdw\.c$"),
    re.compile(r"wcd939x\.h$"),
)

RUNTIME_CLAIM_PHRASES = (
    "runtime ready",
    "runtime-ready",
    "production ready",
    "production-ready",
    "playback works",
    "capture works",
    "runtime validated",
    "runtime-supported",
    "upstream-ready",
)

NEGATION_MARKERS = (
    "not",
    "no",
    "does not",
    "must not",
    "never",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _make_check(
    check_id: str,
    name: str,
    status: str,
    evidence: list[str] | None,
    details: str,
    recommended_action: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "name": name,
        "status": status,
        "evidence": evidence or [],
        "details": details,
        "recommended_action": recommended_action,
    }


def _index_artifacts(run_dir: Path) -> dict[str, Path | None]:
    candidates: dict[str, list[str]] = {
        "patch_lineage": ["patch_lineage.json", "patches/patch_lineage.json"],
        "full_series_validation": ["full_series_validation.json", "patches/full_series_validation.json"],
        "static_gate_governance": ["static_gate/governance_verdict.json"],
        "governance_gate_governance": ["governance_gate/governance_verdict.json"],
        "full_build_result": ["full_build_validation/full_build_result.json"],
        "allowed_sources": ["allowed_sources.json"],
        "fail_closed_items": ["fail_closed_items.json"],
        "runtime_fail_closed_items": ["runtime_fail_closed_items.json"],
        "scoring_result": ["scoring_result_v4.json", "governance_gate/scoring_result_v4.json"],
        "compile_result": ["compile_result.json"],
        "anti_copy_audit": ["anti_copy_audit.json"],
        "verifier_result": ["governance_gate/verifier_result.json", "static_gate/verifier_result.json"],
    }
    indexed: dict[str, Path | None] = {}
    for key, paths in candidates.items():
        indexed[key] = next((run_dir / rel for rel in paths if (run_dir / rel).exists()), None)
    return indexed


def _check_rules_file(rules_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not rules_path.exists():
        check = _make_check(
            "CHECK_RULE_FILE_PARSE",
            "Rule file parse and schema",
            "FAIL",
            [str(rules_path)],
            "Rules file is missing.",
            "Provide a valid promoted rules JSON file.",
        )
        return check, []

    try:
        payload = _load_json(rules_path)
    except json.JSONDecodeError as exc:
        check = _make_check(
            "CHECK_RULE_FILE_PARSE",
            "Rule file parse and schema",
            "FAIL",
            [str(rules_path)],
            f"Rules JSON parse failed: {exc}",
            "Fix JSON syntax in promoted rules file.",
        )
        return check, []

    rules = payload.get("rules") if isinstance(payload, dict) else None
    if not isinstance(rules, list):
        check = _make_check(
            "CHECK_RULE_FILE_PARSE",
            "Rule file parse and schema",
            "FAIL",
            [str(rules_path)],
            "Rules payload must be an object with a list field named 'rules'.",
            "Update rules file schema to include rules list.",
        )
        return check, []

    missing_fields: list[dict[str, Any]] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            missing_fields.append({"index": idx, "missing": sorted(REQUIRED_RULE_FIELDS)})
            continue
        missing = sorted(REQUIRED_RULE_FIELDS - set(rule.keys()))
        if missing:
            missing_fields.append({"index": idx, "rule_id": rule.get("rule_id"), "missing": missing})

    if missing_fields:
        details = {
            "rules_loaded": len(rules),
            "invalid_entries": missing_fields,
        }
        check = _make_check(
            "CHECK_RULE_FILE_PARSE",
            "Rule file parse and schema",
            "FAIL",
            [str(rules_path)],
            json.dumps(details, sort_keys=True),
            "Populate all required rule fields before running compliance checks.",
        )
        return check, []

    check = _make_check(
        "CHECK_RULE_FILE_PARSE",
        "Rule file parse and schema",
        "PASS",
        [str(rules_path)],
        json.dumps({"rules_loaded": len(rules)}, sort_keys=True),
        "No action.",
    )
    return check, rules


def _check_artifact_presence(run_dir: Path, artifact_index: dict[str, Path | None]) -> dict[str, Any]:
    common_keys = [
        "patch_lineage",
        "full_series_validation",
        "static_gate_governance",
        "governance_gate_governance",
        "full_build_result",
        "allowed_sources",
        "fail_closed_items",
        "runtime_fail_closed_items",
        "scoring_result",
    ]
    present = [key for key in common_keys if artifact_index.get(key) is not None]
    missing = [key for key in common_keys if artifact_index.get(key) is None]

    has_governance = artifact_index.get("static_gate_governance") or artifact_index.get("governance_gate_governance")
    has_allowed_sources = artifact_index.get("allowed_sources") is not None

    status = "PASS" if has_governance and has_allowed_sources else "WARN"
    details = {
        "present": {key: _safe_rel(artifact_index[key], run_dir) for key in present},
        "missing": missing,
    }
    action = "Add missing governance and source-allowlist artifacts for stronger compliance coverage."
    if status == "PASS":
        action = "No action required; optional artifacts can improve coverage depth."

    return _make_check(
        "CHECK_RUN_ARTIFACT_PRESENCE",
        "Run directory artifact presence",
        status,
        [_safe_rel(path, run_dir) for path in artifact_index.values() if path],
        json.dumps(details, sort_keys=True),
        action,
    )


def _check_lineage_coverage(run_dir: Path, artifact_index: dict[str, Path | None]) -> dict[str, Any]:
    lineage_path = artifact_index.get("patch_lineage")
    if lineage_path is None:
        return _make_check(
            "CHECK_LINEAGE_COVERAGE",
            "Lineage coverage inference",
            "MISSING",
            [],
            "No patch_lineage artifact found at root or patches/.",
            "Provide patch_lineage.json (or patches/patch_lineage.json).",
        )

    try:
        payload = _load_json(lineage_path)
    except json.JSONDecodeError as exc:
        return _make_check(
            "CHECK_LINEAGE_COVERAGE",
            "Lineage coverage inference",
            "WARN",
            [_safe_rel(lineage_path, run_dir)],
            f"Lineage JSON parse failed: {exc}",
            "Fix lineage JSON format; checker did not infer coverage.",
        )

    if not isinstance(payload, dict):
        return _make_check(
            "CHECK_LINEAGE_COVERAGE",
            "Lineage coverage inference",
            "WARN",
            [_safe_rel(lineage_path, run_dir)],
            "Lineage payload is not a JSON object; schema note recorded.",
            "Normalize lineage schema to JSON object with function/patch mappings.",
        )

    per_function = payload.get("per_function_lineage")
    patches = payload.get("patches")
    schema_note = {
        "lineage_coverage_field": payload.get("lineage_coverage"),
        "has_per_function_lineage": isinstance(per_function, list),
        "per_function_entries": len(per_function) if isinstance(per_function, list) else None,
        "has_patches": isinstance(patches, list),
        "patch_entries": len(patches) if isinstance(patches, list) else None,
    }

    if isinstance(per_function, list) and per_function:
        status = "PASS"
        action = "No action."
    elif isinstance(patches, list) and patches:
        status = "WARN"
        action = "Add per_function_lineage entries for stronger function-level traceability."
    else:
        status = "WARN"
        action = "Lineage exists but contains no detectable entries; populate mapping entries."

    return _make_check(
        "CHECK_LINEAGE_COVERAGE",
        "Lineage coverage inference",
        status,
        [_safe_rel(lineage_path, run_dir)],
        json.dumps(schema_note, sort_keys=True),
        action,
    )


def _collect_runtime_evidence_artifacts(run_dir: Path) -> list[Path]:
    evidence_paths: list[Path] = []
    patterns = [
        "**/*runtime*evidence*.json",
        "**/*hardware*evidence*.json",
        "**/*playback*.log",
        "**/*capture*.log",
        "**/*dmesg*.log",
        "**/*arecord*.log",
        "**/*aplay*.log",
    ]
    for pattern in patterns:
        for path in sorted(run_dir.glob(pattern)):
            if path.is_file() and path.suffix in {".json", ".log", ".md", ".txt"}:
                evidence_paths.append(path)

    unique: dict[str, Path] = {str(path.resolve()): path for path in evidence_paths}
    return [unique[key] for key in sorted(unique.keys())]


def _load_fail_closed_items(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        payload = _load_json(path)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _contains_positive_runtime_claim(path: Path) -> bool:
    text = _read_text(path)
    negated_context_lines = 0
    for line in text.splitlines():
        lower_line = line.lower()
        if any(
            marker in lower_line
            for marker in (
                "what must not be claimed",
                "must not be claimed",
                "do not claim",
                "do not assert",
                "explicit_non_claims",
                "non_claims",
                "runtime_claim_guard",
                "checked_patterns",
                "forbidden_claim_hits",
            )
        ):
            negated_context_lines = 16
            continue

        if negated_context_lines > 0:
            negated_context_lines -= 1
            continue

        for phrase in RUNTIME_CLAIM_PHRASES:
            if phrase in lower_line:
                if not any(marker in lower_line for marker in NEGATION_MARKERS):
                    return True
    return False


def _collect_text_artifacts_for_claim_scan(run_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        rel = _safe_rel(path, run_dir)
        if rel.startswith("logs/"):
            continue
        files.append(path)
        if len(files) >= 200:
            break
    return files


def _check_runtime_sensitive_rules(
    run_dir: Path,
    rules: list[dict[str, Any]],
    artifact_index: dict[str, Path | None],
) -> dict[str, Any]:
    runtime_rules = [rule for rule in rules if bool(rule.get("runtime_evidence_required"))]
    if not runtime_rules:
        return _make_check(
            "CHECK_RUNTIME_SENSITIVE_RULE_EVIDENCE",
            "Runtime-sensitive rule evidence",
            "INFO",
            [],
            "No runtime-sensitive rules were detected in provided rules file.",
            "No action.",
        )

    runtime_evidence = _collect_runtime_evidence_artifacts(run_dir)

    fail_closed_items = _load_fail_closed_items(artifact_index.get("fail_closed_items"))
    runtime_fail_closed_items = _load_fail_closed_items(artifact_index.get("runtime_fail_closed_items"))
    all_fail_closed = fail_closed_items + runtime_fail_closed_items

    preserved_statuses = {"FAIL_CLOSED", "NEEDS_RUNTIME_CONFIRMATION"}
    fail_closed_preserved = bool(all_fail_closed) and all(
        str(item.get("status", "")).strip() in preserved_statuses for item in all_fail_closed
    )

    suspicious_files: list[str] = []
    for artifact in _collect_text_artifacts_for_claim_scan(run_dir):
        if _contains_positive_runtime_claim(artifact):
            suspicious_files.append(_safe_rel(artifact, run_dir))

    details = {
        "runtime_rule_count": len(runtime_rules),
        "runtime_evidence_artifact_count": len(runtime_evidence),
        "runtime_evidence_artifacts": [_safe_rel(path, run_dir) for path in runtime_evidence[:20]],
        "fail_closed_items_count": len(all_fail_closed),
        "fail_closed_preserved": fail_closed_preserved,
        "suspicious_runtime_claim_artifacts": suspicious_files,
    }

    evidence = [_safe_rel(path, run_dir) for path in runtime_evidence[:20]]
    if artifact_index.get("fail_closed_items"):
        evidence.append(_safe_rel(artifact_index["fail_closed_items"], run_dir))
    if artifact_index.get("runtime_fail_closed_items"):
        evidence.append(_safe_rel(artifact_index["runtime_fail_closed_items"], run_dir))

    if runtime_evidence and not suspicious_files:
        status = "INFO"
        action = "Runtime evidence artifacts exist; keep final runtime claims tied to explicit blocker closure evidence IDs."
    elif fail_closed_preserved and not runtime_evidence and not suspicious_files:
        status = "FAIL_CLOSED_OK"
        action = "No runtime evidence found; fail-closed posture preserved as expected."
    elif suspicious_files and not runtime_evidence:
        status = "WARN"
        action = "Potential runtime-positive claims detected without runtime evidence artifacts; verify and correct wording."
    else:
        status = "INFO"
        action = "No runtime-sensitive application was detectable from static artifacts."

    return _make_check(
        "CHECK_RUNTIME_SENSITIVE_RULE_EVIDENCE",
        "Runtime-sensitive rule evidence",
        status,
        evidence,
        json.dumps(details, sort_keys=True),
        action,
    )


def _collect_scan_targets(run_dir: Path) -> list[Path]:
    converted_dir = run_dir / "converted"
    if converted_dir.exists():
        files: list[Path] = []
        for path in sorted(converted_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".c", ".h"} or path.name in {"Kconfig", "Makefile"}:
                files.append(path)
        return files

    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        return sorted([path for path in patches_dir.glob("*.patch") if path.is_file()])

    return []


def _check_vendor_elimination(run_dir: Path) -> dict[str, Any]:
    targets = _collect_scan_targets(run_dir)
    if not targets:
        return _make_check(
            "CHECK_VENDOR_ELIMINATION_HEURISTIC",
            "Vendor token heuristic scan",
            "UNKNOWN",
            [],
            "No converted/ source files or patches/ patch files were found to scan.",
            "Provide converted sources or patch artifacts to enable heuristic scan.",
        )

    token_counts: dict[str, int] = {token: 0 for token, _ in VENDOR_TOKEN_PATTERNS}
    token_locations: dict[str, list[str]] = {token: [] for token, _ in VENDOR_TOKEN_PATTERNS}

    for path in targets:
        text = _read_text(path)
        rel = _safe_rel(path, run_dir)
        for token, pattern in VENDOR_TOKEN_PATTERNS:
            matches = list(pattern.finditer(text))
            if matches:
                token_counts[token] += len(matches)
                token_locations[token].append(rel)

    total_matches = sum(token_counts.values())
    status = "PASS" if total_matches == 0 else "WARN"
    details = {
        "files_scanned": len(targets),
        "token_counts": token_counts,
        "token_locations": {token: sorted(paths) for token, paths in token_locations.items() if paths},
        "heuristic_only": True,
    }
    action = (
        "No vendor-token matches detected by heuristic scan."
        if status == "PASS"
        else "Review flagged files; remove vendor-only dependencies or document intentional usage."
    )

    return _make_check(
        "CHECK_VENDOR_ELIMINATION_HEURISTIC",
        "Vendor token heuristic scan",
        status,
        [_safe_rel(path, run_dir) for path in targets],
        json.dumps(details, sort_keys=True),
        action,
    )


def _check_hidden_target_audit(run_dir: Path, artifact_index: dict[str, Path | None]) -> dict[str, Any]:
    allowed_path = artifact_index.get("allowed_sources")
    if allowed_path is None:
        return _make_check(
            "CHECK_HIDDEN_TARGET_AUDIT",
            "Hidden target access audit",
            "UNKNOWN",
            [],
            "allowed_sources.json is missing; cannot evaluate hidden-target discipline.",
            "Provide allowed_sources.json with forbidden_until_scoring definitions for transfer experiments.",
        )

    try:
        payload = _load_json(allowed_path)
    except json.JSONDecodeError as exc:
        return _make_check(
            "CHECK_HIDDEN_TARGET_AUDIT",
            "Hidden target access audit",
            "WARN",
            [_safe_rel(allowed_path, run_dir)],
            f"allowed_sources.json parse failed: {exc}",
            "Fix allowed_sources.json to evaluate hidden-target discipline.",
        )

    allowed_sources = payload.get("allowed_sources") if isinstance(payload, dict) else None
    forbidden_until_scoring = payload.get("forbidden_until_scoring") if isinstance(payload, dict) else None

    if not isinstance(allowed_sources, list):
        return _make_check(
            "CHECK_HIDDEN_TARGET_AUDIT",
            "Hidden target access audit",
            "WARN",
            [_safe_rel(allowed_path, run_dir)],
            "allowed_sources is missing or not a list.",
            "Use canonical allowed_sources schema.",
        )

    allowed_strings = [str(item) for item in allowed_sources]
    forbidden_strings = [str(item) for item in forbidden_until_scoring] if isinstance(forbidden_until_scoring, list) else []

    forbidden_in_allowed: list[str] = []
    for entry in allowed_strings:
        if any(pattern.search(entry) for pattern in TARGET_HIDDEN_PATTERNS):
            forbidden_in_allowed.append(entry)

    details = {
        "allowed_sources_count": len(allowed_strings),
        "forbidden_until_scoring_count": len(forbidden_strings),
        "forbidden_in_allowed": forbidden_in_allowed,
    }

    if isinstance(forbidden_until_scoring, list):
        if forbidden_in_allowed:
            status = "WARN"
            action = "Remove target files from allowed_sources before scoring stage."
        else:
            status = "PASS"
            action = "No action."
    else:
        status = "UNKNOWN"
        action = "No forbidden_until_scoring list detected; hidden-target discipline cannot be confirmed."

    return _make_check(
        "CHECK_HIDDEN_TARGET_AUDIT",
        "Hidden target access audit",
        status,
        [_safe_rel(allowed_path, run_dir)],
        json.dumps(details, sort_keys=True),
        action,
    )


def _check_downstream_derivation_risk(run_dir: Path, artifact_index: dict[str, Path | None]) -> dict[str, Any]:
    evidence: list[str] = []
    warning_count = 0
    warning_sources: list[str] = []

    anti_copy_path = artifact_index.get("anti_copy_audit")
    if anti_copy_path is not None:
        evidence.append(_safe_rel(anti_copy_path, run_dir))
        try:
            anti_copy_payload = _load_json(anti_copy_path)
        except json.JSONDecodeError as exc:
            return _make_check(
                "CHECK_DOWNSTREAM_DERIVATION_RISK",
                "Downstream derivation risk surfacing",
                "WARN",
                evidence,
                f"anti_copy_audit.json parse failed: {exc}",
                "Fix anti_copy_audit.json parsing issue to restore risk coverage.",
            )

        warning_count += int(anti_copy_payload.get("warning_findings_count", 0) or 0)
        if warning_count:
            warning_sources.append(_safe_rel(anti_copy_path, run_dir))

    verifier_path = artifact_index.get("verifier_result")
    if verifier_path is not None:
        evidence.append(_safe_rel(verifier_path, run_dir))
        try:
            verifier_payload = _load_json(verifier_path)
        except json.JSONDecodeError:
            verifier_payload = None

        if isinstance(verifier_payload, dict):
            findings = verifier_payload.get("findings")
            if isinstance(findings, dict):
                warnings = findings.get("warnings")
                if isinstance(warnings, list):
                    downstream_warnings = [
                        item
                        for item in warnings
                        if isinstance(item, dict)
                        and (
                            str(item.get("group", "")).lower() == "downstream"
                            or "DERIVATION" in str(item.get("severity", "")).upper()
                            or "REUSE" in str(item.get("severity", "")).upper()
                        )
                    ]
                    if downstream_warnings:
                        warning_count = max(warning_count, len(downstream_warnings))
                        warning_sources.append(_safe_rel(verifier_path, run_dir))

    gate_paths = [artifact_index.get("governance_gate_governance"), artifact_index.get("static_gate_governance")]
    for gate_path in gate_paths:
        if gate_path is None:
            continue
        evidence.append(_safe_rel(gate_path, run_dir))
        try:
            gate_payload = _load_json(gate_path)
        except json.JSONDecodeError:
            continue
        if not isinstance(gate_payload, dict):
            continue
        verifier_summary = gate_payload.get("verifier_summary")
        if isinstance(verifier_summary, dict):
            maybe_warnings = int(verifier_summary.get("warning_count", 0) or 0)
            if maybe_warnings > warning_count:
                warning_count = maybe_warnings
                warning_sources.append(_safe_rel(gate_path, run_dir))

    details = {
        "warning_count": warning_count,
        "warning_sources": sorted(set(warning_sources)),
    }

    if warning_count > 0:
        status = "WARN"
        action = "Treat downstream derivation warnings as governance caveats and review anti-copy controls."
    elif evidence:
        status = "PASS"
        action = "No derivation warnings detected in existing audit artifacts."
    else:
        status = "INFO"
        action = "No anti-copy or verifier artifacts found; derivation risk was not directly assessable."

    return _make_check(
        "CHECK_DOWNSTREAM_DERIVATION_RISK",
        "Downstream derivation risk surfacing",
        status,
        sorted(set(evidence)),
        json.dumps(details, sort_keys=True),
        action,
    )


def _check_la_le_terminology(run_dir: Path) -> dict[str, Any]:
    scanned: list[str] = []
    has_la = False
    has_le = False

    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        if path.stat().st_size > 500_000:
            continue
        rel = _safe_rel(path, run_dir)
        if rel.startswith("logs/") or rel.startswith("patches/"):
            continue
        text = _read_text(path)
        scanned.append(rel)
        if re.search(r"\bLA\b", text):
            has_la = True
        if re.search(r"\bLE\b", text):
            has_le = True

    details = {
        "files_scanned": len(scanned),
        "has_LA": has_la,
        "has_LE": has_le,
        "sample_scanned_files": scanned[:20],
    }

    if has_la and has_le:
        status = "PASS"
        action = "No action."
    elif scanned:
        status = "WARN"
        action = "Add explicit LA/LE terminology definitions in planning/governance artifacts."
    else:
        status = "UNKNOWN"
        action = "No suitable markdown/json artifacts found for terminology scan."

    return _make_check(
        "CHECK_LA_LE_TERMINOLOGY",
        "LA/LE terminology presence",
        status,
        scanned[:20],
        json.dumps(details, sort_keys=True),
        action,
    )


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = _load_json(path)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _check_build_gate_summary(run_dir: Path, artifact_index: dict[str, Path | None]) -> dict[str, Any]:
    gate_payload = _load_optional_json(artifact_index.get("governance_gate_governance"))
    static_gate_payload = _load_optional_json(artifact_index.get("static_gate_governance"))
    compile_payload = _load_optional_json(artifact_index.get("compile_result"))
    full_build_payload = _load_optional_json(artifact_index.get("full_build_result"))
    scoring_payload = _load_optional_json(artifact_index.get("scoring_result"))

    gate_verdict = None
    gate_source = None
    if gate_payload is not None:
        gate_verdict = gate_payload.get("verdict")
        gate_source = _safe_rel(artifact_index["governance_gate_governance"], run_dir)
    elif static_gate_payload is not None:
        gate_verdict = static_gate_payload.get("verdict")
        gate_source = _safe_rel(artifact_index["static_gate_governance"], run_dir)

    compile_status = compile_payload.get("status") if compile_payload else None
    full_build_status = full_build_payload.get("status") if full_build_payload else None

    scoring_summary = None
    if scoring_payload is not None:
        if "aggregate" in scoring_payload and isinstance(scoring_payload["aggregate"], dict):
            scoring_summary = {
                "overall_score": scoring_payload["aggregate"].get("overall"),
                "categories": scoring_payload["aggregate"].get("categories"),
            }
        elif "score_summary" in scoring_payload and isinstance(scoring_payload["score_summary"], dict):
            scoring_summary = scoring_payload["score_summary"]

    details = {
        "gate_verdict": gate_verdict,
        "gate_source": gate_source,
        "compile_status": compile_status,
        "full_build_status": full_build_status,
        "scoring_summary": scoring_summary,
    }

    if not any([gate_verdict, compile_status, full_build_status, scoring_summary]):
        status = "UNKNOWN"
        action = "No gate/build/scoring artifacts detected."
    elif gate_verdict == "FAIL":
        status = "FAIL"
        action = "Resolve gate failures before considering compliance healthy."
    elif gate_verdict == "WARN" or (compile_status and "FAIL" in str(compile_status)):
        status = "WARN"
        action = "Review WARN findings; do not treat run as runtime-ready."
    else:
        status = "PASS"
        action = "No action; summary artifacts indicate non-failing static governance state."

    evidence = [
        _safe_rel(path, run_dir)
        for path in [
            artifact_index.get("governance_gate_governance"),
            artifact_index.get("static_gate_governance"),
            artifact_index.get("compile_result"),
            artifact_index.get("full_build_result"),
            artifact_index.get("scoring_result"),
        ]
        if path is not None
    ]

    return _make_check(
        "CHECK_BUILD_GATE_STATUS_SUMMARY",
        "Build/gate/scoring status summary",
        status,
        evidence,
        json.dumps(details, sort_keys=True),
        action,
    )


def _map_rules_to_coverage(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage_map = {
        "WCD-FAMILY-PROMOTED-001": ("PARTIAL", "Architecture reuse is inferred via artifact/governance context, not structural AST validation."),
        "WCD-FAMILY-PROMOTED-002": ("PARTIAL", "Downstream derivation warnings are surfaced from verifier/anti-copy artifacts."),
        "WCD-FAMILY-PROMOTED-003": ("FULL", "Hidden-target allowlist/forbidden-until-scoring checks are implemented."),
        "WCD-FAMILY-PROMOTED-004": ("FULL", "Lineage artifact presence and entry inference are implemented."),
        "WCD-FAMILY-PROMOTED-005": ("PARTIAL", "Runtime evidence gating and fail-closed posture checks are implemented; SDW semantics are not re-verified."),
        "WCD-FAMILY-PROMOTED-006": ("PARTIAL", "Runtime-sensitive fail-closed check is present; regmap lifecycle correctness is not deep-inspected."),
        "WCD-FAMILY-PROMOTED-007": ("PARTIAL", "Derivation risk surfacing is implemented; DAPM topology mapping quality is not recomputed."),
        "WCD-FAMILY-PROMOTED-008": ("PARTIAL", "Runtime-sensitive fail-closed checks cover MBHC/Class-H gating only at artifact level."),
        "WCD-FAMILY-PROMOTED-009": ("PARTIAL", "Runtime claim and heuristic scans may catch workaround language but do not parse semantics fully."),
        "WCD-FAMILY-PROMOTED-010": ("PARTIAL", "Vendor-token heuristic scan is implemented, not a full semantic API-elimination proof."),
        "WCD-FAMILY-PROMOTED-011": ("FULL", "Existing derivation/downstream reuse warnings are surfaced from verifier/anti-copy artifacts."),
        "WCD-FAMILY-PROMOTED-012": ("PARTIAL", "Evidence and runtime-gating signals are checked; DTS/schema correctness is not re-validated."),
        "WCD-FAMILY-PROMOTED-013": ("FULL", "Runtime-sensitive fail-closed policy check is implemented against blocker artifacts."),
    }

    mapped: list[dict[str, Any]] = []
    for rule in rules:
        rule_id = str(rule.get("rule_id", ""))
        coverage, notes = coverage_map.get(rule_id, ("NONE", "No prototype check mapping implemented for this rule ID."))
        mapped.append(
            {
                "rule_id": rule_id,
                "rule_summary": str(rule.get("rule", "")),
                "enforcement": str(rule.get("enforcement", "")),
                "prototype_check_coverage": coverage,
                "notes": notes,
            }
        )
    return mapped


def _apply_strict_mode(checks: list[dict[str, Any]], strict: bool) -> list[dict[str, Any]]:
    if not strict:
        return checks

    strict_fail_ids = {
        "CHECK_LINEAGE_COVERAGE",
        "CHECK_RUNTIME_SENSITIVE_RULE_EVIDENCE",
        "CHECK_HIDDEN_TARGET_AUDIT",
        "CHECK_DOWNSTREAM_DERIVATION_RISK",
    }
    normalized: list[dict[str, Any]] = []
    for check in checks:
        updated = dict(check)
        if updated["check_id"] in strict_fail_ids and updated["status"] in {"WARN", "MISSING"}:
            updated["status"] = "FAIL"
            updated["details"] = f"{updated['details']} | strict_mode_escalation=true"
            updated["recommended_action"] = "Strict mode: resolve this warning/missing state before accepting compliance."
        normalized.append(updated)
    return normalized


def _summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["status"] == "PASS")
    warn_count = sum(1 for check in checks if check["status"] == "WARN")
    fail_count = sum(1 for check in checks if check["status"] == "FAIL")
    info_count = sum(1 for check in checks if check["status"] == "INFO")
    fail_closed_ok_count = sum(1 for check in checks if check["status"] == "FAIL_CLOSED_OK")
    missing_count = sum(1 for check in checks if check["status"] == "MISSING")
    unknown_count = sum(1 for check in checks if check["status"] == "UNKNOWN")

    checks_run = len(checks)
    if fail_count > 0:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "WARN"
    elif checks_run > 0:
        overall = "PASS"
    else:
        overall = "UNKNOWN"

    return {
        "overall_verdict": overall,
        "rules_loaded": 0,
        "checks_run": checks_run,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "info_count": info_count,
        "fail_closed_ok_count": fail_closed_ok_count,
        "missing_count": missing_count,
        "unknown_count": unknown_count,
    }


def run_checker(args: argparse.Namespace) -> dict[str, Any]:
    rules_path = Path(args.rules).resolve()
    run_dir = Path(args.run_dir).resolve()
    output_path = Path(args.output).resolve()

    checks: list[dict[str, Any]] = []
    limitations = [
        "Vendor elimination and runtime-claim checks are heuristic scans and may produce false positives/negatives.",
        "Checker surfaces existing derivation risk from artifacts; it does not recompute full similarity scoring.",
        "Runtime-evidence detection is artifact-name based and does not validate evidence quality.",
        "Lineage check tolerates schema variation and therefore reports inferred coverage only.",
        "Prototype does not modify canonical gate/scorer/verifier verdicts.",
    ]

    rules_check, rules = _check_rules_file(rules_path)
    checks.append(rules_check)

    if not run_dir.exists() or not run_dir.is_dir():
        checks.append(
            _make_check(
                "CHECK_RUN_DIR_EXISTS",
                "Run directory existence",
                "FAIL",
                [str(run_dir)],
                "Run directory does not exist or is not a directory.",
                "Provide a valid run directory path.",
            )
        )
        checks = _apply_strict_mode(checks, args.strict)
        summary = _summarize(checks)
        summary["rules_loaded"] = len(rules)
        report = {
            "artifact": "wcd_rule_pack_compliance_report",
            "generated_at_utc": _utc_now_iso(),
            "checker_version": CHECKER_VERSION,
            "rules_path": str(rules_path),
            "run_dir": str(run_dir),
            "driver_family": args.driver_family,
            "summary": summary,
            "checks": checks,
            "rule_mapping": _map_rules_to_coverage(rules),
            "limitations": limitations,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return report

    artifact_index = _index_artifacts(run_dir)

    checks.append(_check_artifact_presence(run_dir, artifact_index))
    checks.append(_check_lineage_coverage(run_dir, artifact_index))
    checks.append(_check_runtime_sensitive_rules(run_dir, rules, artifact_index))
    checks.append(_check_vendor_elimination(run_dir))
    checks.append(_check_hidden_target_audit(run_dir, artifact_index))
    checks.append(_check_downstream_derivation_risk(run_dir, artifact_index))
    checks.append(_check_la_le_terminology(run_dir))
    checks.append(_check_build_gate_summary(run_dir, artifact_index))

    checks = _apply_strict_mode(checks, args.strict)
    summary = _summarize(checks)
    summary["rules_loaded"] = len(rules)

    report = {
        "artifact": "wcd_rule_pack_compliance_report",
        "generated_at_utc": _utc_now_iso(),
        "checker_version": CHECKER_VERSION,
        "rules_path": str(rules_path),
        "run_dir": str(run_dir),
        "driver_family": args.driver_family,
        "summary": summary,
        "checks": checks,
        "rule_mapping": _map_rules_to_coverage(rules),
        "limitations": limitations,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def _parse_terminology(value: str) -> str:
    if "=" not in value:
        raise argparse.ArgumentTypeError("terminology must be in KEY=value form")
    key, mapped = value.split("=", 1)
    key = key.strip()
    mapped = mapped.strip()
    if not key or not mapped:
        raise argparse.ArgumentTypeError("terminology entries must have non-empty key and value")
    return f"{key}={mapped}"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prototype WCD rule-pack checker")
    parser.add_argument("--rules", required=True, help="Promoted WCD rules JSON")
    parser.add_argument("--run-dir", required=True, help="Run directory to evaluate")
    parser.add_argument("--output", required=True, help="Compliance report output JSON path")
    parser.add_argument("--strict", action="store_true", help="Escalate selected WARN/MISSING checks to FAIL")
    parser.add_argument("--driver-family", default="wcd", help="Driver family label for reporting")
    parser.add_argument(
        "--terminology",
        nargs="*",
        default=["LA=downstream", "LE=upstream"],
        type=_parse_terminology,
        help="Terminology mappings, e.g. LA=downstream LE=upstream",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_path = Path(args.output).resolve()
    try:
        report = run_checker(args)
    except Exception as exc:  # noqa: BLE001 - fail closed on checker execution errors
        output_path.parent.mkdir(parents=True, exist_ok=True)
        error_report = {
            "artifact": "wcd_rule_pack_compliance_report",
            "generated_at_utc": _utc_now_iso(),
            "checker_version": CHECKER_VERSION,
            "rules_path": str(Path(args.rules).resolve()),
            "run_dir": str(Path(args.run_dir).resolve()),
            "driver_family": args.driver_family,
            "summary": {
                "overall_verdict": "FAIL",
                "rules_loaded": 0,
                "checks_run": 0,
                "pass_count": 0,
                "warn_count": 0,
                "fail_count": 1,
                "info_count": 0,
            },
            "checks": [
                _make_check(
                    "CHECKER_EXECUTION",
                    "Checker execution",
                    "FAIL",
                    [],
                    f"Checker execution error: {exc}",
                    "Fix checker input or implementation error and rerun.",
                )
            ],
            "rule_mapping": [],
            "limitations": ["Checker terminated due to execution error."],
        }
        output_path.write_text(json.dumps(error_report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"[wcd-rule-pack-checker] FAIL: {exc}")
        return 1

    print(
        "[wcd-rule-pack-checker] "
        f"{report['summary']['overall_verdict']} "
        f"checks={report['summary']['checks_run']} "
        f"warn={report['summary']['warn_count']} "
        f"fail={report['summary']['fail_count']}"
    )
    return 0 if report["summary"]["overall_verdict"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
