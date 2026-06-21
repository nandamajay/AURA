"""Upstream reviewer simulation prototype (Phase 1).

This module runs deterministic, offline-only review lenses against a run
directory and emits machine/human-readable artifacts for PM and engineers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


ADVISORY_NOTE = "Advisory only - not a replacement for real upstream review."
DEFAULT_BLOCKING_THRESHOLD = 3.0

SEVERITY_ORDER = {
    "BLOCKING": 0,
    "WARN": 1,
    "INFO": 2,
}

BANNED_SYMBOLS = [
    "msm_cdc_pinctrl",
    "msm_cdc_supply",
    "wcdcal_hwdep",
    "bolero_slave",
    "audio_notifier",
    "q6core_",
]


@dataclass
class LensResult:
    lens_name: str
    status: str
    findings: list[dict[str, Any]]
    summary: str
    duration_ms: float


@dataclass
class SimulationReport:
    run_dir: str
    subsystem: str
    lenses_run: list[str]
    lenses_failed: list[str]
    findings: list[dict[str, Any]]
    reviewer_verdicts: dict[str, dict[str, Any]]
    overall_verdict: str
    fix_plan: list[dict[str, Any]]
    advisory_note: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _normalize_severity(value: str) -> str:
    upper = str(value or "").strip().upper()
    if upper in {"WARNING", "WARN"}:
        return "WARN"
    if upper in {"FAIL", "BLOCKING", "ERROR"}:
        return "BLOCKING"
    if upper in {"INFO", "PASS"}:
        return "INFO"
    return "WARN"


def _make_finding(
    *,
    reviewer: str,
    pattern_id: str,
    severity: str,
    text: str,
    evidence: str,
    file_path: str = "",
    lens_name: str = "",
    suggested_action: str = "",
) -> dict[str, Any]:
    return {
        "reviewer": reviewer,
        "pattern_id": pattern_id,
        "severity": _normalize_severity(severity),
        "text": text,
        "evidence": evidence,
        "file": file_path,
        "lens_name": lens_name,
        "suggested_action": suggested_action,
    }


def _status_from_findings(findings: list[dict[str, Any]]) -> str:
    severities = {_normalize_severity(item.get("severity", "")) for item in findings}
    if "BLOCKING" in severities:
        return "FAIL"
    if "WARN" in severities:
        return "WARN"
    return "PASS"


def _safe_regex_search(pattern: str, text: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


def _load_profiles(profiles_dir: Path) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}

    v4_files = sorted(profiles_dir.glob("*_profile_v4.json"))
    if not v4_files:
        # Fallback for environments where v4 files are missing.
        latest_by_slug: dict[str, Path] = {}
        for path in sorted(profiles_dir.glob("*_profile_v*.json")):
            slug = path.name.split("_profile_v", 1)[0]
            latest_by_slug[slug] = path
        v4_files = sorted(latest_by_slug.values())

    for path in v4_files:
        try:
            payload = _load_json(path)
        except Exception:
            continue
        reviewer = str(payload.get("reviewer", "")).strip()
        slug = path.name.split("_profile_v", 1)[0]
        if reviewer:
            profiles[reviewer] = payload
        profiles[slug] = payload
    return profiles


def _reviewer_confidence(reviewer: str, profiles: dict[str, dict[str, Any]]) -> str:
    if reviewer in profiles:
        return str(profiles[reviewer].get("confidence_level", "UNKNOWN"))

    slug = reviewer.lower().replace("-", "_").replace(" ", "_")
    if slug in profiles:
        return str(profiles[slug].get("confidence_level", "UNKNOWN"))

    return "N/A"


def _compute_weighted_score(
    text: str,
    patterns: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    score = 0.0
    fired: list[str] = []
    lower_text = text.lower()
    for pattern in patterns:
        expr = str(pattern.get("pattern", "")).strip()
        if not expr:
            continue
        weight = float(pattern.get("weight", 0.5))
        if weight <= 0.0:
            continue
        if _safe_regex_search(expr, lower_text):
            score += weight
            fired.append(str(pattern.get("pattern_id", expr)))
    return score, fired


def _resolve_patch_root(run_dir: Path) -> Path:
    # For converted/ runs, most governance artifacts are stored one level up.
    candidates = [run_dir, run_dir.parent, run_dir.parent.parent]
    marker_files = {
        "runtime_fail_closed_items.json",
        "fail_closed_items.json",
        "compile_result.json",
        "patch_lineage.json",
        "allowed_sources.json",
    }
    for candidate in candidates:
        if not candidate.exists():
            continue
        if any((candidate / marker).exists() for marker in marker_files):
            return candidate
    return run_dir


def _consume_offline_helpers(subsystem: str, repo_root: Path) -> None:
    """Best-effort invocation of existing offline helpers required for Phase 1.

    This function is intentionally fail-safe and side-effect free. It consumes:
    - reviewer_behavior_model_v1.py offline helpers
    - review_coordinator.py _build_packet()
    - maintainer_intel.py _collect_report()
    - simulation.py _run_one() when runtime dependencies are available
    """

    aura_sdk_src = repo_root / "AURA/workspace/aura-sdk/src"
    if aura_sdk_src.exists() and str(aura_sdk_src) not in sys.path:
        sys.path.insert(0, str(aura_sdk_src))

    try:
        from aura_agents import reviewer_behavior_model_v1 as rbm  # type: ignore

        # Offline pattern helpers only (no network fetch calls).
        rbm.is_objection("Please fix this before next revision.")
        rbm.is_acceptance("Looks good, applied.")
    except Exception:
        pass

    try:
        from aura_agents.review_coordinator import ReviewCoordinatorAgent

        coordinator = ReviewCoordinatorAgent()
        coordinator._build_packet(db_path=":memory:", patch_id="", limit=5)
    except Exception:
        pass

    try:
        from aura_agents.maintainer_intel import MaintainerIntelAgent

        intel = MaintainerIntelAgent()
        intel._collect_report(db_path=":memory:", subsystem_filter=subsystem, limit=5)
    except Exception:
        pass

    try:
        from aura_agents.simulation import SimulationAgent
        from aura_sdk.models.simulation import SimulationType

        sim = SimulationAgent()
        sim.context = None
        sim._run_one(SimulationType.RUNTIME_PM, "state_machine", {})
    except Exception:
        pass


def _load_krysztof_profile(profiles_dir: Path) -> dict[str, Any] | None:
    target = profiles_dir / "krzysztof_kozlowski_profile_v4.json"
    if target.exists():
        return _load_json(target)

    # Fallback to any available version.
    fallback = sorted(profiles_dir.glob("krzysztof_kozlowski_profile_v*.json"))
    if fallback:
        return _load_json(fallback[-1])
    return None


def run_patch_structure_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []

    source_files = sorted(run_dir.rglob("*.c")) + sorted(run_dir.rglob("*.h"))
    source_files = sorted({path.resolve() for path in source_files})

    if not source_files:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="PATCH_STRUCT-000",
                severity="BLOCKING",
                text="No source files found in run directory.",
                evidence=f"run_dir={run_dir}",
                lens_name="patch-structure",
                suggested_action="Provide the converted .c/.h files before running simulation.",
            )
        )
    elif len(source_files) > 10:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="PATCH_STRUCT-010",
                severity="WARN",
                text="Large patch footprint detected (>10 source files).",
                evidence=f"file_count={len(source_files)}",
                lens_name="patch-structure",
                suggested_action="Split into smaller logically reviewable patch series.",
            )
        )

    lineage_candidates = [
        run_dir / "patch_lineage.json",
        run_dir / "patches/patch_lineage.json",
        run_dir.parent / "patch_lineage.json",
        run_dir.parent / "patches/patch_lineage.json",
    ]
    if not any(path.exists() for path in lineage_candidates):
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="PATCH_STRUCT-001",
                severity="WARN",
                text="No patch lineage found - cannot verify change rationale",
                evidence="Checked run_dir and parent for patch_lineage.json.",
                lens_name="patch-structure",
                suggested_action="Provide patch_lineage.json generated from conversion lineage mapping.",
            )
        )

    for c_file in sorted(run_dir.rglob("*.c")):
        c_text = _read_text(c_file)
        rel_path = _safe_rel(c_file, run_dir)
        for symbol in BANNED_SYMBOLS:
            if symbol in c_text:
                findings.append(
                    _make_finding(
                        reviewer="Mark Brown",
                        pattern_id="PATCH_STRUCT-002",
                        severity="BLOCKING",
                        text=f"Banned vendor symbol: {symbol}",
                        evidence=f"{rel_path} contains '{symbol}'",
                        file_path=rel_path,
                        lens_name="patch-structure",
                        suggested_action=f"Replace '{symbol}' with upstream subsystem abstraction.",
                    )
                )

    include_re = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[">]')
    for src in sorted(run_dir.rglob("*")):
        if src.suffix not in {".c", ".h"}:
            continue
        rel_path = _safe_rel(src, run_dir)
        for line_no, line in enumerate(_read_text(src).splitlines(), start=1):
            match = include_re.match(line)
            if not match:
                continue
            inc = match.group(1)
            if "asoc/" in inc.lower() or "dsp/" in inc.lower():
                findings.append(
                    _make_finding(
                        reviewer="Mark Brown",
                        pattern_id="PATCH_STRUCT-006",
                        severity="WARN",
                        text=f"Include path uses vendor namespace: {inc}",
                        evidence=f"{rel_path}:{line_no}",
                        file_path=rel_path,
                        lens_name="patch-structure",
                        suggested_action="Replace with upstream include path or isolate vendor-only dependencies.",
                    )
                )

    patch_dirs = [run_dir / "patches", run_dir.parent / "patches"]
    patch_dir = next((path for path in patch_dirs if path.exists() and path.is_dir()), None)
    if patch_dir:
        for patch_file in sorted(patch_dir.glob("*.patch")):
            text = _read_text(patch_file)
            rel_path = _safe_rel(patch_file, run_dir.parent if patch_file.is_relative_to(run_dir.parent) else run_dir)
            subject = ""
            for line in text.splitlines():
                if line.lower().startswith("subject:"):
                    subject = line.split(":", 1)[1].strip()
                    break

            if subject and len(subject) > 72:
                findings.append(
                    _make_finding(
                        reviewer="Krzysztof Kozlowski",
                        pattern_id="PATCH_STRUCT-003",
                        severity="WARN",
                        text="Patch subject line exceeds 72 characters.",
                        evidence=f"{rel_path} subject_len={len(subject)}",
                        file_path=rel_path,
                        lens_name="patch-structure",
                        suggested_action="Shorten the subject line to <=72 characters.",
                    )
                )

            if "Signed-off-by:" not in text:
                findings.append(
                    _make_finding(
                        reviewer="Vinod Koul",
                        pattern_id="PATCH_STRUCT-004",
                        severity="BLOCKING",
                        text="Missing Signed-off-by trailer.",
                        evidence=f"{rel_path} has no Signed-off-by",
                        file_path=rel_path,
                        lens_name="patch-structure",
                        suggested_action="Add a valid Signed-off-by trailer as required by DCO.",
                    )
                )

            subject_has_fix = bool(re.search(r"\bfix", subject, re.IGNORECASE))
            has_link_or_fixes = ("Link:" in text) or ("Fixes:" in text)
            if subject_has_fix and not has_link_or_fixes:
                findings.append(
                    _make_finding(
                        reviewer="Krzysztof Kozlowski",
                        pattern_id="PATCH_STRUCT-005",
                        severity="WARN",
                        text="Fix patch missing Link:/Fixes: context trailer.",
                        evidence=f"{rel_path} subject='{subject}'",
                        file_path=rel_path,
                        lens_name="patch-structure",
                        suggested_action="Add Link: and/or Fixes: trailers for traceability.",
                    )
                )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"patch-structure findings={len(findings)}"
    return LensResult("patch-structure", status, findings, summary, duration_ms)


def run_build_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []

    kconfig_candidates = [
        run_dir / "Kconfig",
        run_dir / "Kconfig.fragment",
        run_dir.parent / "Kconfig",
        run_dir.parent / "Kconfig.fragment",
    ]
    for kconfig_path in [p for p in kconfig_candidates if p.exists()]:
        text = _read_text(kconfig_path)
        rel_path = _safe_rel(kconfig_path, run_dir.parent if kconfig_path.is_relative_to(run_dir.parent) else run_dir)
        if re.search(r"depends\s+on\s+.*SND_SOC", text, re.IGNORECASE):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-PASS-001",
                    severity="INFO",
                    text="Kconfig has SND_SOC dependency.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                )
            )

        has_select = bool(re.search(r"^\s*select\s+", text, re.IGNORECASE | re.MULTILINE))
        has_depends = bool(re.search(r"^\s*depends\s+on\s+", text, re.IGNORECASE | re.MULTILINE))
        if has_select and not has_depends:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-001",
                    severity="WARN",
                    text="Kconfig uses select without depends on.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Add explicit depends-on constraints matching selected symbols.",
                )
            )

        if re.search(r"depends\s+on\s+.*ARCH_QCOM", text, re.IGNORECASE):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-003",
                    severity="WARN",
                    text="Vendor-specific ARCH_QCOM dependency detected.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Prefer generic dependency gating unless hardware-specific gating is unavoidable.",
                )
            )

    makefile_candidates = [
        run_dir / "Makefile",
        run_dir / "Makefile.fragment",
        run_dir.parent / "Makefile",
        run_dir.parent / "Makefile.fragment",
    ]
    for makefile_path in [p for p in makefile_candidates if p.exists()]:
        text = _read_text(makefile_path)
        rel_path = _safe_rel(makefile_path, run_dir.parent if makefile_path.is_relative_to(run_dir.parent) else run_dir)
        if "obj-$(CONFIG_" in text:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-PASS-002",
                    severity="INFO",
                    text="Makefile uses obj-$(CONFIG_...) pattern.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                )
            )
        if re.search(r"(?:^|\s)(?:/vendor/|/tmp/|\.\./)", text):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-004",
                    severity="WARN",
                    text="Potential hardcoded path detected in Makefile.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Replace hardcoded paths with Kbuild-relative references.",
                )
            )

    compile_candidates = [
        run_dir / "compile_result.json",
        run_dir.parent / "compile_result.json",
        run_dir.parent.parent / "compile_result.json",
    ]
    compile_path = next((p for p in compile_candidates if p.exists()), None)
    if compile_path:
        compile_payload = _load_json(compile_path)
        status_value = str(compile_payload.get("status", "")).strip()
        rel_path = _safe_rel(compile_path, run_dir.parent if compile_path.is_relative_to(run_dir.parent) else run_dir)
        if status_value == "COMPILE_PASS":
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-PASS-003",
                    severity="INFO",
                    text="Compile result indicates COMPILE_PASS.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                )
            )
        elif status_value.startswith("COMPILE_NOT_RUN_"):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-005",
                    severity="WARN",
                    text=f"Compile not fully executed: {status_value}",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Run full compile validation in an environment with full kernel build prerequisites.",
                )
            )
        elif "FAIL" in status_value:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-006",
                    severity="BLOCKING",
                    text=f"Compile failed: {status_value}",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Resolve compile failures before RFC submission.",
                )
            )
    else:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="BUILD-007",
                severity="WARN",
                text="compile_result.json not found.",
                evidence="Checked run_dir and parents for compile_result.json.",
                lens_name="build",
                suggested_action="Attach compile_result.json artifact from validation run.",
            )
        )

    for header in sorted(run_dir.rglob("*.h")):
        text = _read_text(header)
        rel_path = _safe_rel(header, run_dir)
        ifndef = re.search(r"^\s*#ifndef\s+([A-Za-z0-9_]+)\s*$", text, re.MULTILINE)
        if not ifndef:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-002",
                    severity="WARN",
                    text="Header guard missing (#ifndef/#define).",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Add include guards to ensure header self-containment.",
                )
            )
            continue
        macro = ifndef.group(1)
        if not re.search(rf"^\s*#define\s+{re.escape(macro)}\s*$", text, re.MULTILINE):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="BUILD-002",
                    severity="WARN",
                    text="Header guard macro not consistently defined.",
                    evidence=f"{rel_path} macro={macro}",
                    file_path=rel_path,
                    lens_name="build",
                    suggested_action="Ensure matching #ifndef/#define macro pair at top of header.",
                )
            )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"build findings={len(findings)}"
    return LensResult("build", status, findings, summary, duration_ms)


def run_dt_binding_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []

    profiles_dir = Path(context["profiles_dir"])
    profile = _load_krysztof_profile(profiles_dir)
    if not profile:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "dt-binding",
            "FAIL_CLOSED",
            [],
            "Krzysztof profile not found; dt lens closed.",
            duration_ms,
        )

    dt_rules = profile.get("dt_rules", [])
    threshold = float(profile.get("blocking_threshold", DEFAULT_BLOCKING_THRESHOLD))

    dt_tokens = ["compatible", "reg", "#address-cells", "of_match", "device tree", "dt-bindings"]
    candidate_files: list[Path] = []
    for path in sorted(run_dir.rglob("*")):
        if path.suffix.lower() not in {".yaml", ".yml", ".c", ".h"}:
            continue
        text = _read_text(path)
        if any(token in text.lower() for token in dt_tokens):
            candidate_files.append(path)

    for path in candidate_files:
        rel_path = _safe_rel(path, run_dir)
        text = _read_text(path)
        score, fired = _compute_weighted_score(text, dt_rules)
        if score >= threshold and fired:
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-BLOCKING-SCORE",
                    severity="BLOCKING",
                    text=f"DT rule score {score:.2f} exceeds threshold {threshold:.2f}.",
                    evidence=f"{rel_path} fired={','.join(fired)}",
                    file_path=rel_path,
                    lens_name="dt-binding",
                    suggested_action="Address DT schema and binding objections before submission.",
                )
            )

    source_texts = []
    for src in sorted(run_dir.rglob("*.c")) + sorted(run_dir.rglob("*.h")):
        source_texts.append(_read_text(src))
    has_compatible = any("compatible" in text.lower() for text in source_texts)
    yaml_files = sorted(run_dir.rglob("*.yaml")) + sorted(run_dir.rglob("*.yml"))
    has_dt_bindings_dir = (run_dir / "dt-bindings").exists() or (run_dir.parent / "dt-bindings").exists()
    if has_compatible and not yaml_files and not has_dt_bindings_dir:
        findings.append(
            _make_finding(
                reviewer="Krzysztof Kozlowski",
                pattern_id="DT-001",
                severity="WARN",
                text="No DT binding YAML found - required for upstream submission",
                evidence=f"run_dir={run_dir}",
                lens_name="dt-binding",
                suggested_action="Add DT schema YAML for compatible strings used by this driver.",
            )
        )

    has_schema_constraints = False
    for yaml_path in yaml_files:
        yaml_text = _read_text(yaml_path).lower()
        if "additionalproperties: false" in yaml_text or "unevaluatedproperties: false" in yaml_text:
            has_schema_constraints = True
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-PASS-002",
                    severity="INFO",
                    text="DT schema constrains additional/unevaluated properties.",
                    evidence=_safe_rel(yaml_path, run_dir),
                    file_path=_safe_rel(yaml_path, run_dir),
                    lens_name="dt-binding",
                )
            )
            break
    if yaml_files and not has_schema_constraints:
        findings.append(
            _make_finding(
                reviewer="Krzysztof Kozlowski",
                pattern_id="DT-002",
                severity="WARN",
                text="DT schema found, but no additionalProperties/unevaluatedProperties restriction detected.",
                evidence=f"yaml_files={len(yaml_files)}",
                lens_name="dt-binding",
                suggested_action="Tighten schema with additionalProperties:false or unevaluatedProperties:false when applicable.",
            )
        )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"dt-binding findings={len(findings)}"
    return LensResult("dt-binding", status, findings, summary, duration_ms)


def run_upstream_philosophy_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []

    snippets: list[str] = []
    for c_file in sorted(run_dir.rglob("*.c")):
        lines = _read_text(c_file).splitlines()[:200]
        snippets.append("\n".join(lines))
    proposal_text = "\n\n".join(snippets).strip()

    if not proposal_text:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "upstream-philosophy",
            "FAIL_CLOSED",
            [],
            "No .c content available for philosophy assessment.",
            duration_ms,
        )

    # Ensure aura_sdk is importable for BaseAgent dependencies.
    repo_root = Path(context["repo_root"])
    aura_sdk_src = repo_root / "AURA/workspace/aura-sdk/src"
    if aura_sdk_src.exists() and str(aura_sdk_src) not in sys.path:
        sys.path.insert(0, str(aura_sdk_src))

    try:
        from aura_agents.upstream_philosophy import UpstreamPhilosophyAgent
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "upstream-philosophy",
            "FAIL_CLOSED",
            [],
            f"Unable to import UpstreamPhilosophyAgent: {exc}",
            duration_ms,
        )

    try:
        agent = UpstreamPhilosophyAgent()
        principles = agent._principles()
        assessment = agent._assess(proposal_text, principles)
        score = int(assessment.get("score", 0))
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "upstream-philosophy",
            "FAIL_CLOSED",
            [],
            f"lens failed: {exc}",
            duration_ms,
        )

    if score >= 70:
        status = "PASS"
    elif score >= 50:
        status = "WARN"
    else:
        status = "FAIL"

    for check in assessment.get("checks", []):
        if check.get("pass", False):
            continue
        check_id = str(check.get("id", "unknown"))
        check_title = str(check.get("title", check_id))
        expectation = str(check.get("expectation", ""))
        severity = "WARN" if score >= 50 else "BLOCKING"
        findings.append(
            _make_finding(
                reviewer="upstream_philosophy",
                pattern_id=f"UPSTREAM-PHILOSOPHY-{check_id}",
                severity=severity,
                text=f"{check_title}: {expectation}",
                evidence=f"score={score}",
                lens_name="upstream-philosophy",
                suggested_action=f"Address principle gap: {check_title}.",
            )
        )

    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"score={score}/100 failed_checks={len(findings)}"
    return LensResult("upstream-philosophy", status, findings, summary, duration_ms)


def run_rule_pack_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []

    repo_root = Path(context["repo_root"])
    kb_checker_dir = repo_root / "AURA_KB/platform_tools/wcd_rule_pack_checker_01"
    if kb_checker_dir.exists() and str(kb_checker_dir) not in sys.path:
        sys.path.insert(0, str(kb_checker_dir))

    aura_sdk_src = repo_root / "AURA/workspace/aura-sdk/src"
    if aura_sdk_src.exists() and str(aura_sdk_src) not in sys.path:
        sys.path.insert(0, str(aura_sdk_src))

    try:
        import wcd_rule_pack_checker as checker  # type: ignore
    except Exception:
        try:
            from aura_agents import wcd_rule_pack_checker as checker  # type: ignore
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000.0
            return LensResult(
                "rule-pack",
                "FAIL_CLOSED",
                [],
                f"rule-pack import failed: {exc}",
                duration_ms,
            )

    checker_run_dir = _resolve_patch_root(run_dir)
    checker_output = Path(context["output_dir"]) / "_rule_pack_checker_report.json"
    args = SimpleNamespace(
        rules=str(context["rules_path"]),
        run_dir=str(checker_run_dir),
        output=str(checker_output),
        strict=False,
        driver_family=str(context["subsystem"]),
        terminology=["LA=downstream", "LE=upstream"],
    )

    try:
        report = checker.run_checker(args)
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "rule-pack",
            "FAIL_CLOSED",
            [],
            f"rule-pack checker failed: {exc}",
            duration_ms,
        )

    for check in report.get("checks", []):
        check_id = str(check.get("check_id", "RULEPACK-UNKNOWN"))
        check_name = str(check.get("name", check_id))
        check_status = str(check.get("status", "UNKNOWN")).upper()
        details = str(check.get("details", ""))
        evidence_items = check.get("evidence", []) or []
        evidence = ", ".join(str(item) for item in evidence_items[:5]) if evidence_items else details[:240]

        if check_status == "FAIL":
            severity = "BLOCKING"
        elif check_status in {"WARN", "MISSING", "UNKNOWN", "FAIL_CLOSED_OK"}:
            severity = "WARN"
        else:
            continue

        findings.append(
            _make_finding(
                reviewer="wcd_rule_pack",
                pattern_id=check_id,
                severity=severity,
                text=f"{check_name} ({check_status})",
                evidence=evidence,
                lens_name="rule-pack",
                suggested_action=str(check.get("recommended_action", "Review rule pack output and address findings.")),
            )
        )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = (
        f"rule-pack verdict={report.get('summary', {}).get('overall_verdict', 'UNKNOWN')} "
        f"findings={len(findings)} run_dir={checker_run_dir.name}"
    )
    return LensResult("rule-pack", status, findings, summary, duration_ms)


def aggregate_findings(
    *,
    lens_results: list[LensResult],
    profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for lens in lens_results:
        for finding in lens.findings:
            pattern_id = str(finding.get("pattern_id", "UNKNOWN"))
            file_path = str(finding.get("file", ""))
            key = (pattern_id, file_path)
            if key not in merged:
                merged[key] = dict(finding)
                merged[key]["occurrences"] = 1
                merged[key]["lenses"] = [lens.lens_name]
            else:
                merged[key]["occurrences"] += 1
                if lens.lens_name not in merged[key]["lenses"]:
                    merged[key]["lenses"].append(lens.lens_name)

    ordered = sorted(
        merged.values(),
        key=lambda item: (
            SEVERITY_ORDER.get(_normalize_severity(item.get("severity", "WARN")), 99),
            str(item.get("reviewer", "")),
            str(item.get("file", "")),
            str(item.get("pattern_id", "")),
        ),
    )

    for idx, finding in enumerate(ordered, start=1):
        finding["severity"] = _normalize_severity(str(finding.get("severity", "WARN")))
        finding["reviewer_confidence"] = _reviewer_confidence(str(finding.get("reviewer", "")), profiles)
        finding["finding_id"] = f"F-{idx:03d}"
    return ordered


def _build_reviewer_verdicts(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    for finding in findings:
        reviewer = str(finding.get("reviewer", "unknown"))
        severity = _normalize_severity(str(finding.get("severity", "WARN")))
        verdicts.setdefault(
            reviewer,
            {
                "verdict": "READY",
                "blocking_count": 0,
                "warning_count": 0,
                "info_count": 0,
            },
        )
        if severity == "BLOCKING":
            verdicts[reviewer]["blocking_count"] += 1
        elif severity == "WARN":
            verdicts[reviewer]["warning_count"] += 1
        else:
            verdicts[reviewer]["info_count"] += 1

    for reviewer, stats in verdicts.items():
        if stats["blocking_count"] > 0:
            stats["verdict"] = "BLOCKED"
        elif stats["warning_count"] > 0:
            stats["verdict"] = "NEEDS_WORK"
        else:
            stats["verdict"] = "READY"
        verdicts[reviewer] = stats
    return verdicts


def _build_fix_plan(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fix_plan: list[dict[str, Any]] = []
    for finding in findings:
        severity = _normalize_severity(str(finding.get("severity", "WARN")))
        if severity == "INFO":
            continue
        priority = "P0" if severity == "BLOCKING" else "P1"
        action = str(finding.get("suggested_action", "")).strip()
        if not action:
            action = f"Address {finding.get('pattern_id')} finding: {finding.get('text')}"
        fix_plan.append(
            {
                "priority": priority,
                "finding_id": finding.get("finding_id", ""),
                "action": action,
                "owner": "driver_author",
                "reviewer_signal": f"{finding.get('reviewer')} ({finding.get('reviewer_confidence', 'N/A')})",
            }
        )
    return fix_plan


def _compute_overall_verdict(
    findings: list[dict[str, Any]],
    lenses_failed: list[str],
) -> str:
    blocking = sum(1 for finding in findings if finding.get("severity") == "BLOCKING")
    warnings = sum(1 for finding in findings if finding.get("severity") == "WARN")
    if blocking > 0:
        return "BLOCKED"
    if warnings > 0 or lenses_failed:
        return "NEEDS_WORK"
    return "READY_FOR_RFC"


def write_outputs(report: SimulationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) Full machine-readable report.
    report_path = output_dir / "upstream_review_report.json"
    report_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    # 2) Human-readable reviewer comments.
    by_reviewer: dict[str, list[dict[str, Any]]] = {}
    for finding in report.findings:
        by_reviewer.setdefault(str(finding.get("reviewer", "unknown")), []).append(finding)

    comments_lines = [
        "## Simulated Review Comments",
        "",
        f"> {ADVISORY_NOTE}",
        "",
    ]
    for reviewer in sorted(by_reviewer.keys()):
        reviewer_findings = by_reviewer[reviewer]
        confidence = reviewer_findings[0].get("reviewer_confidence", "N/A")
        comments_lines.append(f"### {reviewer} ({confidence} confidence)")
        comments_lines.append("")
        for finding in reviewer_findings:
            tag = finding.get("severity", "WARN")
            file_label = str(finding.get("file", "")).strip() or "<run-scope>"
            comments_lines.append(f"**[{tag}] {finding.get('finding_id')}** `{file_label}`")
            comments_lines.append(str(finding.get("text", "")))
            comments_lines.append(
                f"*Pattern: {finding.get('pattern_id')} | Confidence: {finding.get('reviewer_confidence', 'N/A')}*"
            )
            comments_lines.append("")
    (output_dir / "review_comments.md").write_text("\n".join(comments_lines).rstrip() + "\n", encoding="utf-8")

    # 3) Ordered fix plan.
    plan_lines = [
        "## Fix Plan (Priority Order)",
        "",
        "| Priority | ID | Action | Reviewer Signal |",
        "|---|---|---|---|",
    ]
    for item in report.fix_plan:
        plan_lines.append(
            f"| {item['priority']} | {item['finding_id']} | {item['action']} | {item['reviewer_signal']} |"
        )
    if len(report.fix_plan) == 0:
        plan_lines.append("| P2 | - | No actionable issues detected | n/a |")
    (output_dir / "fix_plan.md").write_text("\n".join(plan_lines).rstrip() + "\n", encoding="utf-8")

    # 4) PM verdict summary.
    blocking_count = sum(1 for item in report.findings if item.get("severity") == "BLOCKING")
    warning_count = sum(1 for item in report.findings if item.get("severity") == "WARN")
    pm_lines = [
        "## PM Review Verdict",
        "",
        f"**Overall:** {report.overall_verdict}",
        f"**Blocking findings:** {blocking_count}",
        f"**Warning findings:** {warning_count}",
        f"**Lenses run:** {len(report.lenses_run)} / {len(report.lenses_run) - len(report.lenses_failed)} succeeded",
        "",
        "### Reviewer Verdicts",
    ]
    for reviewer in sorted(report.reviewer_verdicts.keys()):
        rv = report.reviewer_verdicts[reviewer]
        pm_lines.append(
            f"- {reviewer}: {rv['blocking_count']} blocking, {rv['warning_count']} warnings ({rv['verdict']})"
        )
    pm_lines.extend(
        [
            "",
            "### Advisory Note",
            ADVISORY_NOTE,
            "Runtime-sensitive items remain FAIL_CLOSED pending hardware evidence.",
        ]
    )
    (output_dir / "pm_review_verdict.md").write_text("\n".join(pm_lines).rstrip() + "\n", encoding="utf-8")


LENS_REGISTRY: dict[str, Callable[[Path, dict[str, Any]], LensResult]] = {
    "patch-structure": run_patch_structure_lens,
    "dt-binding": run_dt_binding_lens,
    "upstream-philosophy": run_upstream_philosophy_lens,
    "rule-pack": run_rule_pack_lens,
    "build": run_build_lens,
}


def run_lens(name: str, run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    try:
        fn = LENS_REGISTRY[name]
        result = fn(run_dir, context)
        if result.duration_ms <= 0.0:
            result.duration_ms = (time.perf_counter() - start) * 1000.0
        return result
    except Exception as exc:  # noqa: BLE001
        return LensResult(
            lens_name=name,
            status="FAIL_CLOSED",
            findings=[],
            summary=f"lens failed: {exc}",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline upstream reviewer simulation prototype")
    parser.add_argument("--run-dir", required=True, help="Driver run directory to review")
    parser.add_argument("--subsystem", required=True, help="Subsystem label (e.g. soundwire-codec)")
    parser.add_argument("--lenses", required=True, help="Comma-separated lens list")
    parser.add_argument("--profiles", required=True, help="Directory containing reviewer profiles")
    parser.add_argument("--rules", required=True, help="Promoted WCD rule pack JSON path")
    parser.add_argument("--output", required=True, help="Output directory for report artifacts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    profiles_dir = Path(args.profiles).resolve()
    rules_path = Path(args.rules).resolve()
    output_dir = Path(args.output).resolve()

    if not run_dir.exists():
        raise SystemExit(f"run directory not found: {run_dir}")
    if not profiles_dir.exists():
        raise SystemExit(f"profiles directory not found: {profiles_dir}")
    if not rules_path.exists():
        raise SystemExit(f"rules file not found: {rules_path}")

    requested_lenses = [item.strip() for item in str(args.lenses).split(",") if item.strip()]
    unsupported = [item for item in requested_lenses if item not in LENS_REGISTRY]
    if unsupported:
        raise SystemExit(f"unsupported lenses: {', '.join(unsupported)}")

    repo_root = Path(__file__).resolve().parents[4]
    profiles = _load_profiles(profiles_dir)
    _consume_offline_helpers(str(args.subsystem), repo_root)
    context = {
        "repo_root": str(repo_root),
        "profiles_dir": str(profiles_dir),
        "profiles": profiles,
        "rules_path": str(rules_path),
        "subsystem": str(args.subsystem),
        "output_dir": str(output_dir),
    }

    lens_results = [run_lens(name, run_dir, context) for name in requested_lenses]
    lenses_failed = [item.lens_name for item in lens_results if item.status == "FAIL_CLOSED"]

    aggregated = aggregate_findings(lens_results=lens_results, profiles=profiles)
    reviewer_verdicts = _build_reviewer_verdicts(aggregated)
    fix_plan = _build_fix_plan(aggregated)
    overall_verdict = _compute_overall_verdict(aggregated, lenses_failed)

    report = SimulationReport(
        run_dir=str(run_dir),
        subsystem=str(args.subsystem),
        lenses_run=requested_lenses,
        lenses_failed=lenses_failed,
        findings=aggregated,
        reviewer_verdicts=reviewer_verdicts,
        overall_verdict=overall_verdict,
        fix_plan=fix_plan,
        advisory_note=ADVISORY_NOTE,
    )
    write_outputs(report, output_dir)
    print(
        f"[upstream-reviewer-sim] verdict={report.overall_verdict} "
        f"findings={len(report.findings)} "
        f"lenses_failed={len(report.lenses_failed)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
