"""Independent deterministic verifier for AURA conversion artifacts.

This module verifies conversion outputs independently from the execution agent.
It is intentionally separate from the scoring modules: scoring answers "how close
is output to target", while verification asks "was this output produced honestly
without copying a provided reference or leaving output unexplained".
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from aura_agents.conversion_scoring import _extract_function_names, _read_text, _round_score

VERIFIER_ENGINE = "aura_conversion_verifier_v1"
VERIFIER_VERSION = "1.0.0"
DEFAULT_DERIVED_THRESHOLD = 85.0
DEFAULT_COPY_THRESHOLD = 95.0
DEFAULT_LINEAGE_THRESHOLD = 80.0

SOURCE_EXTENSIONS = (".c", ".h")
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
DIGIT_RE = re.compile(r"\d+")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"//.*")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _collect_files(paths: Iterable[str | Path], extensions: tuple[str, ...] = SOURCE_EXTENSIONS) -> list[Path]:
    collected: list[Path] = []
    for item in paths:
        path = Path(item).resolve()
        if path.is_file() and path.suffix in extensions:
            collected.append(path)
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix in extensions:
                    collected.append(child.resolve())
    unique: dict[str, Path] = {str(path): path for path in collected}
    return [unique[key] for key in sorted(unique.keys())]


def _strip_comments(text: str) -> str:
    without_blocks = BLOCK_COMMENT_RE.sub(" ", text)
    return LINE_COMMENT_RE.sub(" ", without_blocks)


def _normalize_identifier(identifier: str) -> str:
    return DIGIT_RE.sub("#", identifier.lower())


def _normalize_text(text: str) -> str:
    text = _strip_comments(text)
    text = HEX_RE.sub("0x#", text)
    text = IDENTIFIER_RE.sub(lambda match: _normalize_identifier(match.group(0)), text)
    text = DIGIT_RE.sub("#", text)
    normalized_lines = []
    for line in text.splitlines():
        collapsed = " ".join(line.split())
        if collapsed:
            normalized_lines.append(collapsed)
    return "\n".join(normalized_lines)


def _line_similarity(left: str, right: str) -> float:
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    if not left_lines and not right_lines:
        return 100.0
    if not left_lines or not right_lines:
        return 0.0
    return difflib.SequenceMatcher(a=left_lines, b=right_lines, autojunk=False).ratio() * 100.0


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"\S+", left))
    right_tokens = set(re.findall(r"\S+", right))
    if not left_tokens and not right_tokens:
        return 100.0
    if not left_tokens or not right_tokens:
        return 0.0
    return (len(left_tokens & right_tokens) / len(left_tokens | right_tokens)) * 100.0


def _similarity_payload(converted_file: Path, reference_file: Path) -> dict[str, Any]:
    converted_text = _read_text(converted_file)
    reference_text = _read_text(reference_file)
    normalized_converted = _normalize_text(converted_text)
    normalized_reference = _normalize_text(reference_text)

    raw_line = _line_similarity(converted_text, reference_text)
    normalized_line = _line_similarity(normalized_converted, normalized_reference)
    normalized_token = _token_jaccard(normalized_converted, normalized_reference)
    max_similarity = max(raw_line, normalized_line, normalized_token)

    return {
        "converted_file": str(converted_file),
        "reference_file": str(reference_file),
        "raw_line_similarity": _round_score(raw_line),
        "normalized_line_similarity": _round_score(normalized_line),
        "normalized_token_similarity": _round_score(normalized_token),
        "max_similarity": _round_score(max_similarity),
        "converted_sha256": _sha256_text(converted_text),
        "reference_sha256": _sha256_text(reference_text),
        "byte_identical": converted_text == reference_text,
    }


def _best_reference_matches(converted_files: list[Path], reference_files: list[Path]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for converted_file in converted_files:
        best: dict[str, Any] | None = None
        for reference_file in reference_files:
            payload = _similarity_payload(converted_file, reference_file)
            if best is None or float(payload["max_similarity"]) > float(best["max_similarity"]):
                best = payload
        if best is not None:
            matches.append(best)
    return matches


def _walk_json_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(_walk_json_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_walk_json_strings(item))
    return strings


def _lineage_function_coverage(converted_files: list[Path], lineage_file: Path | None) -> dict[str, Any]:
    converted_functions: list[str] = []
    for converted_file in converted_files:
        converted_functions.extend(_extract_function_names(_read_text(converted_file)))
    converted_functions = sorted(set(converted_functions))

    if lineage_file is None:
        return {
            "status": "SKIPPED",
            "reason": "no lineage file provided",
            "converted_function_count": len(converted_functions),
            "covered_function_count": 0,
            "coverage": None,
            "uncovered_functions": converted_functions,
        }

    lineage_path = lineage_file.resolve()
    if not lineage_path.exists():
        return {
            "status": "MISSING",
            "reason": f"lineage file not found: {lineage_path}",
            "converted_function_count": len(converted_functions),
            "covered_function_count": 0,
            "coverage": 0.0,
            "uncovered_functions": converted_functions,
        }

    try:
        lineage_payload = json.loads(_read_text(lineage_path))
    except json.JSONDecodeError as exc:
        return {
            "status": "INVALID_JSON",
            "reason": str(exc),
            "converted_function_count": len(converted_functions),
            "covered_function_count": 0,
            "coverage": 0.0,
            "uncovered_functions": converted_functions,
        }

    lineage_text = "\n".join(_walk_json_strings(lineage_payload))
    covered = [name for name in converted_functions if re.search(rf"\b{re.escape(name)}\b", lineage_text)]
    uncovered = sorted(set(converted_functions) - set(covered))
    coverage = 100.0 if not converted_functions else (len(covered) / len(converted_functions)) * 100.0

    return {
        "status": "CHECKED",
        "lineage_file": str(lineage_path),
        "converted_function_count": len(converted_functions),
        "covered_function_count": len(covered),
        "coverage": _round_score(coverage),
        "uncovered_functions": uncovered,
    }


def verify_conversion(
    converted_paths: list[str | Path],
    reference_paths: list[str | Path] | None = None,
    target_paths: list[str | Path] | None = None,
    downstream_paths: list[str | Path] | None = None,
    lineage_file: str | Path | None = None,
    derived_threshold: float = DEFAULT_DERIVED_THRESHOLD,
    copy_threshold: float = DEFAULT_COPY_THRESHOLD,
    lineage_threshold: float = DEFAULT_LINEAGE_THRESHOLD,
) -> dict[str, Any]:
    converted_files = _collect_files(converted_paths)
    reference_files = _collect_files(reference_paths or [])
    target_files = _collect_files(target_paths or [])
    downstream_files = _collect_files(downstream_paths or [])

    candidate_groups = {
        "references": reference_files,
        "targets": target_files,
        "downstream": downstream_files,
    }

    derivation: dict[str, Any] = {}
    derivation_findings: list[dict[str, Any]] = []
    for group_name, files in candidate_groups.items():
        matches = _best_reference_matches(converted_files, files) if files else []
        group_findings = []
        for match in matches:
            similarity = float(match["max_similarity"])
            severity = "PASS"
            if match["byte_identical"] or similarity >= copy_threshold:
                severity = "COPY_RISK"
            elif similarity >= derived_threshold:
                severity = "DERIVATION_RISK"
            item = dict(match)
            item["severity"] = severity
            if severity != "PASS":
                group_findings.append(item)
                derivation_findings.append({"group": group_name, **item})
        derivation[group_name] = {
            "candidate_file_count": len(files),
            "best_matches": matches,
            "findings": group_findings,
        }

    lineage = _lineage_function_coverage(converted_files, Path(lineage_file) if lineage_file else None)

    blocking_findings = [item for item in derivation_findings if item["severity"] == "COPY_RISK"]
    warning_findings = [item for item in derivation_findings if item["severity"] == "DERIVATION_RISK"]
    lineage_coverage = lineage.get("coverage")
    lineage_blocking = lineage_coverage is not None and float(lineage_coverage) < lineage_threshold

    verdict = "PASS"
    if blocking_findings or lineage_blocking:
        verdict = "FAIL"
    elif warning_findings or lineage.get("status") in {"SKIPPED", "MISSING", "INVALID_JSON"}:
        verdict = "WARN"

    return {
        "verifier_engine": VERIFIER_ENGINE,
        "verifier_version": VERIFIER_VERSION,
        "verdict": verdict,
        "thresholds": {
            "derived_threshold": derived_threshold,
            "copy_threshold": copy_threshold,
            "lineage_threshold": lineage_threshold,
        },
        "inputs": {
            "converted_paths": [str(Path(path).resolve()) for path in converted_paths],
            "reference_paths": [str(Path(path).resolve()) for path in (reference_paths or [])],
            "target_paths": [str(Path(path).resolve()) for path in (target_paths or [])],
            "downstream_paths": [str(Path(path).resolve()) for path in (downstream_paths or [])],
            "lineage_file": str(Path(lineage_file).resolve()) if lineage_file else None,
        },
        "collected_files": {
            "converted": [str(path) for path in converted_files],
            "references": [str(path) for path in reference_files],
            "targets": [str(path) for path in target_files],
            "downstream": [str(path) for path in downstream_files],
        },
        "derivation_check": derivation,
        "lineage_check": lineage,
        "findings": {
            "blocking": blocking_findings,
            "warnings": warning_findings,
            "all_derivation_findings": derivation_findings,
        },
        "metadata": {
            "deterministic": True,
            "verifier_logic_sha256": _sha256_text(Path(__file__).read_text(encoding="utf-8")),
        },
    }


def render_verification_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independent deterministic AURA conversion verifier")
    parser.add_argument("--converted", nargs="+", required=True, help="Converted files or directories")
    parser.add_argument("--reference", nargs="*", default=[], help="Allowed reference files or directories")
    parser.add_argument("--target", nargs="*", default=[], help="Target upstream files or directories")
    parser.add_argument("--downstream", nargs="*", default=[], help="Downstream source files or directories")
    parser.add_argument("--lineage", help="Lineage JSON artifact")
    parser.add_argument("--derived-threshold", type=float, default=DEFAULT_DERIVED_THRESHOLD)
    parser.add_argument("--copy-threshold", type=float, default=DEFAULT_COPY_THRESHOLD)
    parser.add_argument("--lineage-threshold", type=float, default=DEFAULT_LINEAGE_THRESHOLD)
    parser.add_argument("--output", help="Optional JSON output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = verify_conversion(
        converted_paths=args.converted,
        reference_paths=args.reference,
        target_paths=args.target,
        downstream_paths=args.downstream,
        lineage_file=args.lineage,
        derived_threshold=args.derived_threshold,
        copy_threshold=args.copy_threshold,
        lineage_threshold=args.lineage_threshold,
    )
    rendered = render_verification_json(report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
