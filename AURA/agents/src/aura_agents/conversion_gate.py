"""Canonical governance gate for AURA conversion runs.

The gate is the repo-owned checker that turns conversion governance from
self-attestation into executable verification. It does not generate patches.
It validates existing conversion artifacts by running deterministic scoring and
verification, then emits one canonical governance_verdict.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aura_agents.conversion_verifier import render_verification_json, verify_conversion
from aura_agents.multifile_scoring import render_multifile_score_json, score_multifile

GATE_ENGINE = "aura_conversion_gate_v1"
GATE_VERSION = "1.0.0"
REVIEWER_SIM_ADVISORY_NOTE = "Advisory only - not a replacement for real upstream review."


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(64 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return payload


def _validate_allowed_sources(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"allowed_sources.json missing: {path}")
    payload = _load_json_object(path, "allowed_sources")
    sources = payload.get("allowed_sources")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("allowed_sources must contain a non-empty allowed_sources list")
    invalid = [item for item in sources if not isinstance(item, str) or not item.strip()]
    if invalid:
        raise RuntimeError("allowed_sources contains non-string or empty entries")
    return payload


def _copy_input_manifest(args: argparse.Namespace) -> dict[str, Any]:
    allowed_path = Path(args.allowed_sources).resolve()
    allowed_payload = _validate_allowed_sources(allowed_path)
    return {
        "allowed_sources_file": str(allowed_path),
        "allowed_sources_sha256": _sha256_file(allowed_path),
        "allowed_sources_count": len(allowed_payload.get("allowed_sources", [])),
        "converted_dir": str(Path(args.converted_dir).resolve()),
        "upstream_dir": str(Path(args.upstream_dir).resolve()) if args.upstream_dir else None,
        "file_map": str(Path(args.file_map).resolve()) if args.file_map else None,
        "references": [str(Path(path).resolve()) for path in args.reference],
        "targets": [str(Path(path).resolve()) for path in args.target],
        "downstream": [str(Path(path).resolve()) for path in args.downstream],
        "lineage": str(Path(args.lineage).resolve()) if args.lineage else None,
        "banned_symbols": str(Path(args.banned_symbols).resolve()) if args.banned_symbols else None,
        "dt_binding": str(Path(args.dt_binding).resolve()) if args.dt_binding else None,
    }


def _stage_target_files(run_dir: Path, target_paths: list[str]) -> Path | None:
    if not target_paths:
        return None

    target_dir = run_dir / "upstream_target"
    target_dir.mkdir(parents=True, exist_ok=True)
    staged = 0
    for item in target_paths:
        path = Path(item).resolve()
        if path.is_file():
            shutil.copy2(path, target_dir / path.name)
            staged += 1
    return target_dir if staged else None


def _find_repo_root_for_reviewer_sim() -> Path:
    """Find the repo root by walking upward until AURA_KB is visible."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "AURA_KB").is_dir():
            return candidate
    return Path(__file__).resolve().parents[4]


def _run_reviewer_sim(
    converted_dir: str,
    run_dir: Path,
    profiles_dir: Path | None,
    subsystem: str,
) -> dict[str, Any] | None:
    """Run upstream reviewer simulation in advisory mode.

    Returns reviewer_sim_summary dict or None if sim cannot run.
    Never raises - all errors are caught and returned as a degraded summary.
    Gate verdict is never modified by this function's output.
    """

    try:
        # Lazy import keeps gate importable even if simulation module is broken.
        from aura_agents import upstream_reviewer_sim

        repo_root = _find_repo_root_for_reviewer_sim()
        converted_path = Path(converted_dir).resolve()
        resolved_profiles_dir = (
            profiles_dir.resolve()
            if profiles_dir is not None
            else (repo_root / "AURA_KB/reviewer_profiles/processed").resolve()
        )
        if not converted_path.exists():
            raise RuntimeError(f"converted_dir not found: {converted_path}")
        if not resolved_profiles_dir.exists():
            raise RuntimeError(f"reviewer sim profiles dir not found: {resolved_profiles_dir}")

        profiles = upstream_reviewer_sim._load_profiles(resolved_profiles_dir)
        context = {
            "repo_root": str(repo_root),
            "profiles_dir": str(resolved_profiles_dir),
            "profiles": profiles,
            "rules_path": str(upstream_reviewer_sim._default_rules_path(repo_root).resolve()),
            "subsystem": str(subsystem),
            "subsystem_focus_profiles": upstream_reviewer_sim.SUBSYSTEM_REVIEWER_MAP,
            "output_dir": str(run_dir),
        }
        lens_names = ["patch-structure", "dt-binding", "asoc-subsystem"]
        lens_results = [upstream_reviewer_sim.run_lens(name, converted_path, context) for name in lens_names]
        aggregated = upstream_reviewer_sim.aggregate_findings(lens_results=lens_results, profiles=profiles)

        blocking_count = sum(1 for finding in aggregated if finding.get("severity") == "BLOCKING")
        warn_count = sum(1 for finding in aggregated if finding.get("severity") == "WARN")
        info_count = sum(1 for finding in aggregated if finding.get("severity") == "INFO")

        if blocking_count > 0:
            sim_verdict = "BLOCKED"
        elif warn_count > 0:
            sim_verdict = "NEEDS_WORK"
        else:
            sim_verdict = "LGTM"

        top_findings: list[dict[str, Any]] = []
        for finding in aggregated[:5]:
            lenses = finding.get("lenses") if isinstance(finding.get("lenses"), list) else []
            top_findings.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "severity": finding.get("severity"),
                    "text": finding.get("text"),
                    "lens_name": finding.get("lens_name") or (lenses[0] if lenses else ""),
                    "reviewer": finding.get("reviewer"),
                    "suggested_action": finding.get("suggested_action") or f"Address {finding.get('pattern_id', 'reviewer-sim')} finding.",
                    "pattern_id": finding.get("pattern_id"),
                    "file": finding.get("file"),
                }
            )
        profiles_used = sorted(path.name for path in resolved_profiles_dir.glob("*.json") if path.is_file())

        return {
            "advisory_note": REVIEWER_SIM_ADVISORY_NOTE,
            "sim_verdict": sim_verdict,
            "blocking_count": blocking_count,
            "warn_count": warn_count,
            "info_count": info_count,
            "gate_impact": "NONE",
            "gate_impact_reason": "Sim findings are advisory. Core verdict is unchanged.",
            "top_findings": top_findings,
            "profiles_used": profiles_used,
            "subsystem": str(subsystem),
            "sim_run_dir": str(converted_path),
            "generated_at_utc": _utc_now_iso(),
        }
    except Exception as exc:  # noqa: BLE001 - reviewer sim is advisory and must not break the gate.
        return {
            "advisory_note": REVIEWER_SIM_ADVISORY_NOTE,
            "sim_verdict": "ERROR",
            "error": str(exc),
            "blocking_count": 0,
            "warn_count": 0,
            "info_count": 0,
            "gate_impact": "NONE",
            "gate_impact_reason": "Sim error — core verdict unchanged.",
            "top_findings": [],
            "profiles_used": [],
            "subsystem": str(subsystem),
            "sim_run_dir": str(Path(converted_dir).resolve()),
            "generated_at_utc": _utc_now_iso(),
        }


def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = _copy_input_manifest(args)
    manifest_path = run_dir / "gate_input_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    target_paths = list(args.target)
    staged_upstream_dir = None if args.upstream_dir else _stage_target_files(run_dir, target_paths)
    scoring_upstream_dir = args.upstream_dir or (str(staged_upstream_dir) if staged_upstream_dir else None)

    score_report: dict[str, Any] | None = None
    score_path: Path | None = None
    if scoring_upstream_dir:
        score_report = score_multifile(
            upstream_dir=scoring_upstream_dir,
            converted_dir=args.converted_dir,
            file_map_path=args.file_map,
            banned_symbols_file=args.banned_symbols,
            dt_binding_file=args.dt_binding,
        )
        score_path = run_dir / "scoring_result_v4.json"
        score_path.write_text(render_multifile_score_json(score_report), encoding="utf-8")

    if scoring_upstream_dir and not target_paths:
        target_paths = [scoring_upstream_dir]

    verifier_report = verify_conversion(
        converted_paths=[args.converted_dir],
        reference_paths=args.reference,
        target_paths=target_paths,
        downstream_paths=args.downstream,
        lineage_file=args.lineage,
        derived_threshold=args.derived_threshold,
        copy_threshold=args.copy_threshold,
        lineage_threshold=args.lineage_threshold,
    )
    verifier_path = run_dir / "verifier_result.json"
    verifier_path.write_text(render_verification_json(verifier_report), encoding="utf-8")

    verdict = "PASS"
    reasons: list[str] = []
    if verifier_report["verdict"] == "FAIL":
        verdict = "FAIL"
        reasons.append("verifier_failed")
    elif verifier_report["verdict"] == "WARN":
        verdict = "WARN"
        reasons.append("verifier_warned")

    if score_report is None:
        if verdict == "PASS":
            verdict = "WARN"
        reasons.append("scoring_skipped_no_upstream_dir")

    result = {
        "gate_engine": GATE_ENGINE,
        "gate_version": GATE_VERSION,
        "generated_at_utc": _utc_now_iso(),
        "verdict": verdict,
        "reasons": reasons,
        "run_dir": str(run_dir),
        "inputs_manifest": str(manifest_path),
        "artifacts": {
            "scoring_result": str(score_path) if score_path else None,
            "verifier_result": str(verifier_path),
            "staged_upstream_dir": str(staged_upstream_dir) if staged_upstream_dir else None,
        },
        "score_summary": None if score_report is None else {
            "overall": score_report["aggregate"]["overall"],
            "categories": score_report["aggregate"]["categories"],
            "paired_source_files": score_report["file_pairing"]["paired_source_files"],
            "unpaired_upstream_source_files": score_report["file_pairing"]["unpaired_upstream_source_files"],
        },
        "verifier_summary": {
            "verdict": verifier_report["verdict"],
            "blocking_count": len(verifier_report["findings"]["blocking"]),
            "warning_count": len(verifier_report["findings"]["warnings"]),
            "lineage_status": verifier_report["lineage_check"]["status"],
            "lineage_coverage": verifier_report["lineage_check"].get("coverage"),
        },
        "policy": {
            "fail_if_verifier_fails": True,
            "require_allowed_sources_file": True,
            "self_attestation_trusted": False,
        },
    }

    reviewer_sim_enabled = bool(getattr(args, "reviewer_sim", False))
    if reviewer_sim_enabled:
        profiles_override = getattr(args, "reviewer_sim_profiles_dir", None)
        reviewer_sim_summary = _run_reviewer_sim(
            converted_dir=args.converted_dir,
            run_dir=run_dir,
            profiles_dir=Path(profiles_override) if profiles_override else None,
            subsystem=str(getattr(args, "reviewer_sim_subsystem", "asoc")),
        )
    else:
        reviewer_sim_summary = None
    result["reviewer_sim_summary"] = reviewer_sim_summary

    # Invariant: reviewer sim must never change the core verdict.
    assert result["verdict"] in ("PASS", "WARN", "FAIL"), "Gate verdict corrupted"

    verdict_path = run_dir / "governance_verdict.json"
    verdict_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AURA conversion governance gate")
    parser.add_argument("--run-dir", required=True, help="Tracked gate output directory")
    parser.add_argument("--allowed-sources", required=True, help="allowed_sources.json path")
    parser.add_argument("--converted-dir", required=True, help="Converted output directory")
    parser.add_argument("--upstream-dir", help="Upstream target directory for multi-file scoring")
    parser.add_argument("--file-map", help="Optional file map for multi-file scoring")
    parser.add_argument("--reference", nargs="*", default=[], help="Reference files/directories used during conversion")
    parser.add_argument("--target", nargs="*", default=[], help="Target files/directories for copy checks")
    parser.add_argument("--downstream", nargs="*", default=[], help="Downstream source files/directories")
    parser.add_argument("--lineage", help="Lineage JSON artifact")
    parser.add_argument("--banned-symbols", help="Optional banned symbols JSON")
    parser.add_argument("--dt-binding", help="Optional DT binding YAML")
    parser.add_argument(
        "--reviewer-sim",
        action="store_true",
        default=False,
        help="Run upstream reviewer simulation in advisory mode and embed summary in verdict (advisory only, never changes verdict).",
    )
    parser.add_argument(
        "--reviewer-sim-profiles-dir",
        default=None,
        help="Path to reviewer profiles directory for simulation (default: auto-detect from repo root).",
    )
    parser.add_argument(
        "--reviewer-sim-subsystem",
        default="asoc",
        help="Subsystem hint for reviewer simulation (default: asoc).",
    )
    parser.add_argument("--derived-threshold", type=float, default=85.0)
    parser.add_argument("--copy-threshold", type=float, default=95.0)
    parser.add_argument("--lineage-threshold", type=float, default=80.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_gate(args)
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed on any gate error.
        result = {
            "gate_engine": GATE_ENGINE,
            "gate_version": GATE_VERSION,
            "generated_at_utc": _utc_now_iso(),
            "verdict": "FAIL",
            "reasons": ["gate_error"],
            "error": str(exc),
            "policy": {
                "fail_if_verifier_fails": True,
                "require_allowed_sources_file": True,
                "self_attestation_trusted": False,
            },
        }
        try:
            run_dir = Path(args.run_dir).resolve()
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "governance_verdict.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            result["run_dir"] = str(run_dir)
        except Exception:
            pass
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
