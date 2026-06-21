"""Upstream reviewer simulation prototype (Phase 1).

This module runs deterministic, offline-only review lenses against a run
directory and emits machine/human-readable artifacts for PM and engineers.
"""

from __future__ import annotations

import argparse
import enum
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


# Python 3.10 compatibility shim for modules expecting enum.StrEnum (3.11+).
if not hasattr(enum, "StrEnum"):
    class _CompatStrEnum(str, enum.Enum):
        """Compatibility replacement for enum.StrEnum on Python < 3.11."""

    enum.StrEnum = _CompatStrEnum  # type: ignore[attr-defined]


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

DEFAULT_LENS_SEQUENCE = [
    "patch-structure",
    "dt-binding",
    "upstream-philosophy",
    "rule-pack",
    "build",
]

SUBSYSTEM_REVIEWER_MAP = {
    "asoc": ["Mark Brown", "Liam Girdwood", "Pierre-Louis Bossart", "Vinod Koul"],
    "soundwire-codec": ["Mark Brown", "Pierre-Louis Bossart", "Vinod Koul"],
    "dt-bindings": ["Krzysztof Kozlowski", "Rob Herring"],
    "pinctrl": ["Linus Walleij", "Bjorn Andersson"],
    "qcom-platform": ["Bjorn Andersson", "Konrad Dybcio"],
}

PROFILE_SOURCE_MAP = {
    "Mark Brown": "mark_brown_profile_v4",
    "Pierre-Louis Bossart": "pierre_louis_bossart_profile_v4",
    "Vinod Koul": "vinod_koul_profile_v4",
    "Krzysztof Kozlowski": "krzysztof_kozlowski_profile_v4",
}


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
    profile_source: str = "",
    suggested_filename: str = "",
) -> dict[str, Any]:
    finding = {
        "reviewer": reviewer,
        "pattern_id": pattern_id,
        "severity": _normalize_severity(severity),
        "text": text,
        "evidence": evidence,
        "file": file_path,
        "lens_name": lens_name,
        "suggested_action": suggested_action,
    }
    if profile_source:
        finding["profile_source"] = profile_source
    if suggested_filename:
        finding["suggested_filename"] = suggested_filename
    return finding


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


def _preferred_code_roots(run_dir: Path) -> list[Path]:
    roots: list[Path] = []
    converted = run_dir / "converted"
    governance_target = run_dir / "governance_gate/upstream_target"
    if converted.exists() and converted.is_dir():
        roots.append(converted)
    if governance_target.exists() and governance_target.is_dir():
        roots.append(governance_target)
    if not roots:
        roots.append(run_dir)
    return roots


def _collect_code_files(run_dir: Path, suffixes: tuple[str, ...]) -> list[Path]:
    files: dict[str, Path] = {}
    for root in _preferred_code_roots(run_dir):
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in suffixes:
                continue
            files[str(path.resolve())] = path
    return [files[key] for key in sorted(files.keys())]


def _collect_patch_files(run_dir: Path) -> list[Path]:
    patch_root = _resolve_patch_root(run_dir)
    candidates = [
        patch_root / "patches",
        run_dir / "patches",
        run_dir.parent / "patches",
    ]
    files: dict[str, Path] = {}
    for directory in candidates:
        if not directory.exists() or not directory.is_dir():
            continue
        for patch_file in sorted(directory.glob("*.patch")):
            files[str(patch_file.resolve())] = patch_file
    return [files[key] for key in sorted(files.keys())]


def _normalize_subsystem(subsystem: str) -> str:
    return subsystem.strip().lower().replace("_", "-")


def _primary_reviewers_for_subsystem(subsystem: str) -> set[str]:
    normalized = _normalize_subsystem(subsystem)
    for key, reviewers in SUBSYSTEM_REVIEWER_MAP.items():
        if key in normalized or normalized in key:
            return set(reviewers)
    return set()


def _resolve_requested_lenses(lenses_arg: str | None, subsystem: str) -> list[str]:
    requested: list[str] = []
    if lenses_arg and lenses_arg.strip().lower() != "auto":
        requested = [part.strip() for part in lenses_arg.split(",") if part.strip()]
    else:
        requested = list(DEFAULT_LENS_SEQUENCE)

    normalized_subsystem = _normalize_subsystem(subsystem)
    if ("asoc" in normalized_subsystem or "soundwire-codec" in normalized_subsystem) and (
        "asoc-subsystem" not in requested
    ):
        requested.append("asoc-subsystem")
    return requested


def _default_rules_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "AURA_KB/drivers/wcd_codec_family/rule_promotion_01/wcd_codec_family_rules_promoted.json"
    )


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
        from aura_agents.dts_bindings import DTSBindingsAgent

        dts_agent = DTSBindingsAgent()
        dts_agent.rules_path = str(repo_root / "AURA_KB/platform_tools")
        dts_agent._load_rule_mappings()
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


def run_asoc_subsystem_lens(run_dir: Path, context: dict[str, Any]) -> LensResult:
    start = time.perf_counter()
    findings: list[dict[str, Any]] = []
    subsystem = _normalize_subsystem(str(context.get("subsystem", "")))

    c_files = _collect_code_files(run_dir, (".c",))
    h_files = _collect_code_files(run_dir, (".h",))
    if not c_files and not h_files:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return LensResult(
            "asoc-subsystem",
            "FAIL_CLOSED",
            [],
            "No .c/.h files found for ASoC subsystem checks.",
            duration_ms,
        )

    all_c_text = "\n\n".join(_read_text(path) for path in c_files)
    has_component_driver = False
    has_dapm_widgets = False
    has_dapm_routes = False
    has_devm_usage = False
    has_sdw_ops = False
    compatible_strings: set[str] = set()
    seen_bad_compat: set[str] = set()

    for c_file in c_files:
        text = _read_text(c_file)
        rel_path = _safe_rel(c_file, run_dir)

        # Mark Brown profile checks.
        if "MODULE_LICENSE(" not in text:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="ASOC-MARK-001",
                    severity="BLOCKING",
                    text="MODULE_LICENSE() is missing from module source.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Add MODULE_LICENSE() to satisfy module metadata requirements.",
                    profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                )
            )
        if "MODULE_DESCRIPTION(" not in text:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="ASOC-MARK-002",
                    severity="WARN",
                    text="MODULE_DESCRIPTION() is missing from module source.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Add MODULE_DESCRIPTION() for maintainability and clarity.",
                    profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                )
            )
        if "MODULE_AUTHOR(" not in text:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="ASOC-MARK-003",
                    severity="WARN",
                    text="MODULE_AUTHOR() is missing from module source.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Add MODULE_AUTHOR() to preserve attribution metadata.",
                    profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                )
            )

        if "snd_soc_component_driver" in text:
            has_component_driver = True
        if "snd_soc_codec_driver" in text:
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="ASOC-MARK-004",
                    severity="BLOCKING",
                    text="Legacy snd_soc_codec_driver detected; use snd_soc_component_driver.",
                    evidence=rel_path,
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Migrate legacy codec driver registration to snd_soc_component_driver.",
                    profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                )
            )

        if "snd_soc_dapm_widget" in text:
            has_dapm_widgets = True
            if re.search(r"snd_soc_dapm_widget[\s\S]*?\[[^\]]*\]\s*=\s*\{\s*\}", text):
                findings.append(
                    _make_finding(
                        reviewer="Mark Brown",
                        pattern_id="ASOC-MARK-005",
                        severity="WARN",
                        text="DAPM widget array is empty.",
                        evidence=rel_path,
                        file_path=rel_path,
                        lens_name="asoc-subsystem",
                        suggested_action="Populate snd_soc_dapm_widget entries or remove unused array.",
                        profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                    )
                )
        if "snd_soc_dapm_route" in text:
            has_dapm_routes = True
            if re.search(r"snd_soc_dapm_route[\s\S]*?\[[^\]]*\]\s*=\s*\{\s*\}", text):
                findings.append(
                    _make_finding(
                        reviewer="Mark Brown",
                        pattern_id="ASOC-MARK-006",
                        severity="WARN",
                        text="DAPM route array is empty.",
                        evidence=rel_path,
                        file_path=rel_path,
                        lens_name="asoc-subsystem",
                        suggested_action="Populate snd_soc_dapm_route entries or remove unused array.",
                        profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                    )
                )

        # Pierre-Louis Bossart profile checks.
        if "sdw_slave_ops" in text:
            has_sdw_ops = True
            required_callbacks = {
                "update_status": "ASOC-BOSSART-001",
                "bus_config": "ASOC-BOSSART-002",
                "hw_params": "ASOC-BOSSART-003",
            }
            for callback, pattern_id in required_callbacks.items():
                if f".{callback}" not in text:
                    findings.append(
                        _make_finding(
                            reviewer="Pierre-Louis Bossart",
                            pattern_id=pattern_id,
                            severity="WARN",
                            text=f"sdw_slave_ops missing .{callback} callback.",
                            evidence=rel_path,
                            file_path=rel_path,
                            lens_name="asoc-subsystem",
                            suggested_action=f"Add .{callback} callback to sdw_slave_ops implementation.",
                            profile_source=PROFILE_SOURCE_MAP["Pierre-Louis Bossart"],
                        )
                    )

        # Vinod Koul profile checks.
        enable_count = len(re.findall(r"\bpm_runtime_enable\s*\(", text))
        disable_count = len(re.findall(r"\bpm_runtime_disable\s*\(", text))
        if enable_count > 0 and disable_count == 0:
            findings.append(
                _make_finding(
                    reviewer="Vinod Koul",
                    pattern_id="ASOC-VINOD-001",
                    severity="BLOCKING",
                    text="pm_runtime_enable() found without matching pm_runtime_disable().",
                    evidence=f"{rel_path} enable_count={enable_count} disable_count={disable_count}",
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Ensure pm_runtime_disable() is called in remove/error paths.",
                    profile_source=PROFILE_SOURCE_MAP["Vinod Koul"],
                )
            )
        if disable_count > 0 and enable_count == 0:
            findings.append(
                _make_finding(
                    reviewer="Vinod Koul",
                    pattern_id="ASOC-VINOD-002",
                    severity="WARN",
                    text="pm_runtime_disable() found without pm_runtime_enable().",
                    evidence=f"{rel_path} enable_count={enable_count} disable_count={disable_count}",
                    file_path=rel_path,
                    lens_name="asoc-subsystem",
                    suggested_action="Ensure runtime PM lifecycle is balanced in probe/remove flow.",
                    profile_source=PROFILE_SOURCE_MAP["Vinod Koul"],
                )
            )
        if "devm_" in text:
            has_devm_usage = True

        # Krzysztof Kozlowski profile checks.
        for match in re.finditer(r'"([A-Za-z0-9][A-Za-z0-9._+-]*,[A-Za-z0-9][A-Za-z0-9._+-]*)"', text):
            compatible = match.group(1)
            compatible_strings.add(compatible)
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*,[a-z0-9]+(?:-[a-z0-9]+)*", compatible):
                seen_bad_compat.add(compatible)
                findings.append(
                    _make_finding(
                        reviewer="Krzysztof Kozlowski",
                        pattern_id="ASOC-KRZYSZTOF-001",
                        severity="WARN",
                        text=f"Non-canonical DT compatible format: {compatible}",
                        evidence=rel_path,
                        file_path=rel_path,
                        lens_name="asoc-subsystem",
                        suggested_action="Use vendor,device lowercase compatible format with hyphen-separated tokens.",
                        profile_source=PROFILE_SOURCE_MAP["Krzysztof Kozlowski"],
                    )
                )

    if not has_component_driver:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="ASOC-MARK-007",
                severity="WARN",
                text="snd_soc_component_driver definition not detected.",
                evidence="No snd_soc_component_driver symbol in scanned C files.",
                lens_name="asoc-subsystem",
                suggested_action="Use snd_soc_component_driver for modern ASoC codec integration.",
                profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
            )
        )

    if not has_dapm_widgets:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="ASOC-MARK-008",
                severity="WARN",
                text="No snd_soc_dapm_widget array found.",
                evidence="DAPM widgets were not detected in scanned codec sources.",
                lens_name="asoc-subsystem",
                suggested_action="Define snd_soc_dapm_widget entries for power graph visibility.",
                profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
            )
        )
    if not has_dapm_routes:
        findings.append(
            _make_finding(
                reviewer="Mark Brown",
                pattern_id="ASOC-MARK-009",
                severity="WARN",
                text="No snd_soc_dapm_route array found.",
                evidence="DAPM routes were not detected in scanned codec sources.",
                lens_name="asoc-subsystem",
                suggested_action="Define snd_soc_dapm_route entries to connect audio paths explicitly.",
                profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
            )
        )

    if ("soundwire" in subsystem or "sdw" in all_c_text.lower()) and not has_sdw_ops:
        findings.append(
            _make_finding(
                reviewer="Pierre-Louis Bossart",
                pattern_id="ASOC-BOSSART-004",
                severity="WARN",
                text="No sdw_slave_ops structure detected in SoundWire-oriented subsystem run.",
                evidence="Expected sdw_slave_ops callbacks were not found in codec C files.",
                lens_name="asoc-subsystem",
                suggested_action="Provide sdw_slave_ops callbacks for SoundWire slave behavior.",
                profile_source=PROFILE_SOURCE_MAP["Pierre-Louis Bossart"],
            )
        )

    if not re.search(r"\b(?:devm_)?sdw_register_slave\s*\(", all_c_text):
        findings.append(
            _make_finding(
                reviewer="Pierre-Louis Bossart",
                pattern_id="ASOC-BOSSART-005",
                severity="WARN",
                text="No sdw_register_slave()/devm_sdw_register_slave() call detected.",
                evidence="SoundWire slave registration helper was not observed in C sources.",
                lens_name="asoc-subsystem",
                suggested_action="Ensure SoundWire slave registration helper is used during probe.",
                profile_source=PROFILE_SOURCE_MAP["Pierre-Louis Bossart"],
            )
        )

    if not has_devm_usage:
        findings.append(
            _make_finding(
                reviewer="Vinod Koul",
                pattern_id="ASOC-VINOD-003",
                severity="WARN",
                text="No devm_* managed resource APIs detected.",
                evidence="devm_ prefix calls were not observed in scanned C files.",
                lens_name="asoc-subsystem",
                suggested_action="Prefer devm_* managed APIs for resource lifecycle cleanup.",
                profile_source=PROFILE_SOURCE_MAP["Vinod Koul"],
            )
        )

    if compatible_strings and not re.search(r"\bstruct\s+of_device_id\b", all_c_text):
        findings.append(
            _make_finding(
                reviewer="Krzysztof Kozlowski",
                pattern_id="ASOC-KRZYSZTOF-002",
                severity="WARN",
                text="DT compatible strings found but struct of_device_id table is missing.",
                evidence=f"compatible_count={len(compatible_strings)}",
                lens_name="asoc-subsystem",
                suggested_action="Add struct of_device_id table and bind it via of_match_table.",
                profile_source=PROFILE_SOURCE_MAP["Krzysztof Kozlowski"],
            )
        )

    for patch_file in _collect_patch_files(run_dir):
        patch_text = _read_text(patch_file)
        rel_patch = _safe_rel(patch_file, _resolve_patch_root(run_dir))
        if not re.search(r"^Signed-off-by:\s+.+", patch_text, re.MULTILINE):
            findings.append(
                _make_finding(
                    reviewer="Mark Brown",
                    pattern_id="ASOC-MARK-010",
                    severity="BLOCKING",
                    text="Patch is missing Signed-off-by trailer.",
                    evidence=rel_patch,
                    file_path=rel_patch,
                    lens_name="asoc-subsystem",
                    suggested_action="Add Signed-off-by trailer to comply with submission process requirements.",
                    profile_source=PROFILE_SOURCE_MAP["Mark Brown"],
                )
            )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"asoc-subsystem findings={len(findings)}"
    return LensResult("asoc-subsystem", status, findings, summary, duration_ms)


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

    profile_source = PROFILE_SOURCE_MAP["Krzysztof Kozlowski"]
    dt_rules = profile.get("dt_rules", [])
    threshold = float(profile.get("blocking_threshold", DEFAULT_BLOCKING_THRESHOLD))

    dt_tokens = ["compatible", "reg", "#address-cells", "of_match", "device tree", "dt-bindings"]
    candidate_files: list[Path] = []
    for path in sorted(_resolve_patch_root(run_dir).rglob("*")):
        if path.suffix.lower() not in {".yaml", ".yml", ".c", ".h"}:
            continue
        text = _read_text(path)
        if any(token in text.lower() for token in dt_tokens):
            candidate_files.append(path)

    for path in candidate_files:
        rel_path = _safe_rel(path, _resolve_patch_root(run_dir))
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
                    profile_source=profile_source,
                )
            )

    code_files = _collect_code_files(run_dir, (".c", ".h"))
    source_texts = [_read_text(src) for src in code_files]
    has_compatible = any("compatible" in text.lower() for text in source_texts)
    root_dir = _resolve_patch_root(run_dir)
    yaml_files = sorted(root_dir.rglob("*.yaml")) + sorted(root_dir.rglob("*.yml"))
    has_dt_bindings_dir = (root_dir / "dt-bindings").exists() or (run_dir / "dt-bindings").exists()

    def _suggest_binding_filename() -> str:
        match = re.search(r'"([a-z0-9]+(?:-[a-z0-9]+)*,[a-z0-9]+(?:-[a-z0-9]+)*)"', "\n".join(source_texts))
        if match:
            compatible = match.group(1)
        else:
            basename = next((path.stem for path in code_files if re.search(r"(wcd|wsa)\d+", path.stem, re.IGNORECASE)), "")
            if basename:
                compatible = f"qcom,{basename.lower()}"
            else:
                compatible = "qcom,unknown-codec"
        return f"Documentation/devicetree/bindings/sound/{compatible}.yaml"

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
                profile_source=profile_source,
                suggested_filename=_suggest_binding_filename(),
            )
        )

    for yaml_path in yaml_files:
        rel_yaml = _safe_rel(yaml_path, root_dir)
        yaml_text = _read_text(yaml_path)

        if not re.search(r"^\s*\$schema\s*:\s*.+", yaml_text, re.MULTILINE):
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-003",
                    severity="WARN",
                    text="DT binding YAML missing $schema field.",
                    evidence=rel_yaml,
                    file_path=rel_yaml,
                    lens_name="dt-binding",
                    suggested_action="Add $schema reference at top-level of YAML binding.",
                    profile_source=profile_source,
                )
            )
        if not re.search(r"^\s*title\s*:\s*.+", yaml_text, re.MULTILINE):
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-004",
                    severity="WARN",
                    text="DT binding YAML missing title field.",
                    evidence=rel_yaml,
                    file_path=rel_yaml,
                    lens_name="dt-binding",
                    suggested_action="Add descriptive title for the DT binding.",
                    profile_source=profile_source,
                )
            )

        maintainers_match = re.search(
            r"^\s*maintainers\s*:\s*(?:\n\s*-\s+.+)+",
            yaml_text,
            re.MULTILINE,
        )
        if not maintainers_match:
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-005",
                    severity="WARN",
                    text="DT binding YAML missing non-empty maintainers list.",
                    evidence=rel_yaml,
                    file_path=rel_yaml,
                    lens_name="dt-binding",
                    suggested_action="Add maintainers list with at least one maintainer entry.",
                    profile_source=profile_source,
                )
            )

        has_compatible_field = bool(re.search(r"^\s*compatible\s*:\s*", yaml_text, re.MULTILINE))
        has_compatible_constraint = bool(
            re.search(
                r"^\s*compatible\s*:\s*(?:\n[ \t]+[^\n]*){0,20}\n[ \t]+(?:const|enum)\s*:",
                yaml_text,
                re.MULTILINE,
            )
        )
        if has_compatible_field and not has_compatible_constraint:
            findings.append(
                _make_finding(
                    reviewer="Krzysztof Kozlowski",
                    pattern_id="DT-006",
                    severity="BLOCKING",
                    text="compatible property is unconstrained; expected const:/enum: constraint.",
                    evidence=rel_yaml,
                    file_path=rel_yaml,
                    lens_name="dt-binding",
                    suggested_action="Constrain compatible with const: or enum: in binding schema.",
                    profile_source=profile_source,
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
                    evidence=_safe_rel(yaml_path, root_dir),
                    file_path=_safe_rel(yaml_path, root_dir),
                    lens_name="dt-binding",
                    profile_source=profile_source,
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
                profile_source=profile_source,
            )
        )

    status = _status_from_findings(findings)
    duration_ms = (time.perf_counter() - start) * 1000.0
    summary = f"dt-binding findings={len(findings)}"
    return LensResult("dt-binding", status, findings, summary, duration_ms)


def _fallback_philosophy_principles() -> list[dict[str, str]]:
    return [
        {
            "id": "minimal_scope",
            "title": "Minimal and reviewable scope",
            "expectation": "Change set should be small, targeted, and split logically.",
        },
        {
            "id": "clear_rationale",
            "title": "Clear rationale",
            "expectation": "Proposal should explain why the change is required.",
        },
        {
            "id": "generic_abstractions",
            "title": "Prefer generic abstractions",
            "expectation": "Avoid vendor-only hooks when kernel abstractions exist.",
        },
        {
            "id": "dt_binding_hygiene",
            "title": "Device-tree binding hygiene",
            "expectation": "DT bindings should map to documented YAML schema expectations.",
        },
        {
            "id": "test_evidence",
            "title": "Test evidence present",
            "expectation": "Validation evidence should be included (build/runtime/checks).",
        },
        {
            "id": "maintainability",
            "title": "Long-term maintainability",
            "expectation": "Avoid temporary hacks and hidden behavior.",
        },
    ]


def _fallback_philosophy_assess(text: str, principles: list[dict[str, str]]) -> dict[str, Any]:
    lower = text.lower()
    checks: list[dict[str, Any]] = []

    def has_any(*terms: str) -> bool:
        return any(term in lower for term in terms)

    for principle in principles:
        pid = principle["id"]
        if pid == "minimal_scope":
            ok = has_any("minimal", "small", "incremental", "split")
            confidence = 0.8 if ok else 0.45
        elif pid == "clear_rationale":
            ok = has_any("because", "rationale", "reason", "motivation")
            confidence = 0.85 if ok else 0.5
        elif pid == "generic_abstractions":
            bad = has_any("vendor-only", "private api", "downstream-only", "hack")
            ok = not bad
            confidence = 0.75 if ok else 0.25
        elif pid == "dt_binding_hygiene":
            ok = has_any("binding", "yaml", "device-tree", "dt")
            confidence = 0.8 if ok else 0.45
        elif pid == "test_evidence":
            ok = has_any("test", "checkpatch", "sparse", "dtbs_check", "validated")
            confidence = 0.9 if ok else 0.35
        elif pid == "maintainability":
            bad = has_any("temporary", "workaround", "quick fix", "hack")
            ok = not bad
            confidence = 0.8 if ok else 0.2
        else:
            ok = False
            confidence = 0.0

        checks.append(
            {
                "id": pid,
                "title": principle["title"],
                "expectation": principle["expectation"],
                "pass": ok,
                "confidence": round(confidence, 2),
            }
        )

    passed = sum(1 for check in checks if check["pass"])
    score = int(round((passed / max(len(checks), 1)) * 100))
    return {"score": score, "checks": checks}


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

    import_mode = "agent"
    try:
        from aura_agents.upstream_philosophy import UpstreamPhilosophyAgent

        agent = UpstreamPhilosophyAgent()
        principles = agent._principles()
        assessment = agent._assess(proposal_text, principles)
        score = int(assessment.get("score", 0))
    except Exception:
        # Python 3.10 compatibility fallback: evaluate with the same rubric
        # without importing BaseAgent/aura_sdk runtime dependencies.
        import_mode = "fallback"
        try:
            principles = _fallback_philosophy_principles()
            assessment = _fallback_philosophy_assess(proposal_text, principles)
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
    summary = f"score={score}/100 failed_checks={len(findings)} mode={import_mode}"
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


def _build_reviewer_verdicts(
    findings: list[dict[str, Any]],
    subsystem: str,
) -> dict[str, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    primary_reviewers = _primary_reviewers_for_subsystem(subsystem)
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
                "focus_role": "primary" if reviewer in primary_reviewers else "secondary",
            },
        )
        if severity == "BLOCKING":
            verdicts[reviewer]["blocking_count"] += 1
        elif severity == "WARN":
            verdicts[reviewer]["warning_count"] += 1
        else:
            verdicts[reviewer]["info_count"] += 1

    for reviewer, stats in verdicts.items():
        stats["focus_role"] = "primary" if reviewer in primary_reviewers else "secondary"
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
        f"> {ADVISORY_NOTE}",
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
            f"- {reviewer} [{rv.get('focus_role', 'secondary')}]: "
            f"{rv['blocking_count']} blocking, {rv['warning_count']} warnings ({rv['verdict']})"
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
    "asoc-subsystem": run_asoc_subsystem_lens,
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
    parser.add_argument(
        "--lenses",
        default="auto",
        help="Comma-separated lens list. Use 'auto' (default) for subsystem-aware selection.",
    )
    parser.add_argument(
        "--profiles",
        "--profiles-dir",
        dest="profiles",
        required=True,
        help="Directory containing reviewer profiles",
    )
    parser.add_argument(
        "--rules",
        default="",
        help="Promoted WCD rule pack JSON path (optional; defaults to promoted rules in repository).",
    )
    parser.add_argument(
        "--output",
        "--output-dir",
        dest="output",
        required=True,
        help="Output directory for report artifacts",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[4]
    run_dir = Path(args.run_dir).resolve()
    profiles_dir = Path(args.profiles).resolve()
    rules_path = Path(args.rules).resolve() if str(args.rules).strip() else _default_rules_path(repo_root).resolve()
    output_dir = Path(args.output).resolve()

    if not run_dir.exists():
        raise SystemExit(f"run directory not found: {run_dir}")
    if not profiles_dir.exists():
        raise SystemExit(f"profiles directory not found: {profiles_dir}")
    if not rules_path.exists() and ("rule-pack" in str(args.lenses).lower() or str(args.lenses).strip().lower() == "auto"):
        raise SystemExit(f"rules file not found: {rules_path}")

    requested_lenses = _resolve_requested_lenses(str(args.lenses), str(args.subsystem))
    unsupported = [item for item in requested_lenses if item not in LENS_REGISTRY]
    if unsupported:
        raise SystemExit(f"unsupported lenses: {', '.join(unsupported)}")

    profiles = _load_profiles(profiles_dir)
    _consume_offline_helpers(str(args.subsystem), repo_root)
    context = {
        "repo_root": str(repo_root),
        "profiles_dir": str(profiles_dir),
        "profiles": profiles,
        "rules_path": str(rules_path),
        "subsystem": str(args.subsystem),
        "subsystem_focus_profiles": SUBSYSTEM_REVIEWER_MAP,
        "output_dir": str(output_dir),
    }

    lens_results = [run_lens(name, run_dir, context) for name in requested_lenses]
    lenses_failed = [item.lens_name for item in lens_results if item.status == "FAIL_CLOSED"]

    aggregated = aggregate_findings(lens_results=lens_results, profiles=profiles)
    reviewer_verdicts = _build_reviewer_verdicts(aggregated, str(args.subsystem))
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
