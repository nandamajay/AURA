"""Multi-file conversion scoring for AURA driver comparisons (v4).

Extends the single-file scorer (conversion_scoring.py v3) to handle
multi-file drivers like WCD codecs.

Design:
- Each upstream file is paired with a converted file via explicit mapping or stem matching.
- Per-file scores are computed using the existing single-file scorer.
- Aggregate score is a weighted arithmetic mean (weighted by upstream line count).
- Unpaired upstream files score 0 across all categories.
- Extra converted files (no upstream pair) are reported but don't penalize the score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from aura_agents.conversion_scoring import (
    CATEGORY_ORDER,
    SCORING_ENGINE_VERSION,
    _read_text,
    _round_score,
    _scoring_logic_sha256,
    render_score_json,
    score_conversion,
)

MULTIFILE_SCORING_ENGINE = "aura_multifile_scoring_v1"
MULTIFILE_SCORING_VERSION = "1.0.0"


def _file_line_count(path: Path) -> int:
    """Count lines in a file."""
    text = _read_text(path)
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _stem_normalize(filename: str) -> str:
    """Normalize a filename stem for fuzzy matching.

    Handles common downstream/upstream naming differences:
    - wcd937x_slave.c -> wcd937x-slave -> wcd937x-sdw (mapped separately)
    - lpass-cdc-rx-macro.c -> lpass-rx-macro (mapped separately)
    """
    stem = Path(filename).stem
    # Normalize underscores to hyphens for comparison
    return stem.replace("_", "-").lower()


def _auto_pair_files(
    upstream_dir: Path,
    converted_dir: Path,
    upstream_extensions: tuple[str, ...] = (".c", ".h"),
    converted_extensions: tuple[str, ...] = (".c", ".h"),
) -> tuple[list[tuple[Path, Path]], list[Path], list[Path]]:
    """Auto-pair files by matching stems.

    Returns:
        - paired: list of (upstream_file, converted_file) tuples
        - unpaired_upstream: upstream files with no converted match
        - unpaired_converted: converted files with no upstream match
    """
    upstream_files = sorted(
        f for f in upstream_dir.iterdir()
        if f.is_file() and f.suffix in upstream_extensions
    )
    converted_files = sorted(
        f for f in converted_dir.iterdir()
        if f.is_file() and f.suffix in converted_extensions
    )

    # Build lookup by normalized stem + suffix
    converted_lookup: dict[str, Path] = {}
    for f in converted_files:
        key = _stem_normalize(f.name) + f.suffix
        converted_lookup[key] = f

    paired: list[tuple[Path, Path]] = []
    unpaired_upstream: list[Path] = []
    used_converted: set[str] = set()

    for uf in upstream_files:
        key = _stem_normalize(uf.name) + uf.suffix
        if key in converted_lookup:
            paired.append((uf, converted_lookup[key]))
            used_converted.add(key)
        else:
            unpaired_upstream.append(uf)

    unpaired_converted = [
        f for f in converted_files
        if (_stem_normalize(f.name) + f.suffix) not in used_converted
    ]

    return paired, unpaired_upstream, unpaired_converted


def _load_file_map(file_map_path: Path) -> dict[str, str]:
    """Load explicit file mapping JSON.

    Format: {"upstream_filename": "converted_filename", ...}
    Example: {"wcd937x-sdw.c": "wcd937x_slave.c", "wcd937x.h": "internal.h"}
    """
    text = _read_text(file_map_path)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"File map must be a JSON object, got {type(data).__name__}")
    return {str(k): str(v) for k, v in data.items()}


def _pair_with_map(
    upstream_dir: Path,
    converted_dir: Path,
    file_map: dict[str, str],
    upstream_extensions: tuple[str, ...] = (".c", ".h"),
    converted_extensions: tuple[str, ...] = (".c", ".h"),
) -> tuple[list[tuple[Path, Path]], list[Path], list[Path]]:
    """Pair files using explicit mapping, falling back to stem matching for unmapped files."""
    upstream_files = sorted(
        f for f in upstream_dir.iterdir()
        if f.is_file() and f.suffix in upstream_extensions
    )
    converted_files = sorted(
        f for f in converted_dir.iterdir()
        if f.is_file() and f.suffix in converted_extensions
    )

    converted_by_name: dict[str, Path] = {f.name: f for f in converted_files}

    paired: list[tuple[Path, Path]] = []
    unpaired_upstream: list[Path] = []
    used_converted: set[str] = set()

    for uf in upstream_files:
        # Check explicit map first
        if uf.name in file_map:
            mapped_name = file_map[uf.name]
            if mapped_name in converted_by_name:
                paired.append((uf, converted_by_name[mapped_name]))
                used_converted.add(mapped_name)
                continue
            else:
                # Mapped file doesn't exist
                unpaired_upstream.append(uf)
                continue

        # Fall back to exact name match
        if uf.name in converted_by_name:
            paired.append((uf, converted_by_name[uf.name]))
            used_converted.add(uf.name)
            continue

        # Fall back to stem-normalized match
        norm_key = _stem_normalize(uf.name) + uf.suffix
        for cf in converted_files:
            if cf.name not in used_converted:
                cf_key = _stem_normalize(cf.name) + cf.suffix
                if cf_key == norm_key:
                    paired.append((uf, cf))
                    used_converted.add(cf.name)
                    break
        else:
            unpaired_upstream.append(uf)

    unpaired_converted = [f for f in converted_files if f.name not in used_converted]

    return paired, unpaired_upstream, unpaired_converted


def _zero_score_report(upstream_path: Path) -> dict[str, Any]:
    """Generate a zero-score report for an unpaired upstream file."""
    categories = {}
    for cat_name in CATEGORY_ORDER:
        categories[cat_name] = {"score": 0.0, "reason": "no_converted_pair"}
    return {
        "upstream_file": str(upstream_path),
        "converted_file": None,
        "status": "UNPAIRED",
        "line_count": _file_line_count(upstream_path),
        "categories": categories,
        "overall": {"score": 0.0},
    }


def score_multifile(
    upstream_dir: str | Path,
    converted_dir: str | Path,
    file_map_path: str | Path | None = None,
    banned_symbols_file: str | Path | None = None,
    dt_binding_file: str | Path | None = None,
    source_extensions: tuple[str, ...] = (".c",),
    header_extensions: tuple[str, ...] = (".h",),
) -> dict[str, Any]:
    """Score a multi-file converted driver against multi-file upstream target.

    Args:
        upstream_dir: Directory containing upstream source files.
        converted_dir: Directory containing converted source files.
        file_map_path: Optional JSON mapping upstream filenames to converted filenames.
        banned_symbols_file: Optional banned symbols JSON for vendor elimination.
        dt_binding_file: Optional DT binding YAML.
        source_extensions: File extensions to score (default: .c only; headers handled separately).
        header_extensions: File extensions treated as headers for register scanning.

    Returns:
        Comprehensive scoring report with per-file and aggregate scores.
    """
    up_dir = Path(upstream_dir).resolve()
    cv_dir = Path(converted_dir).resolve()

    if not up_dir.is_dir():
        raise ValueError(f"Upstream directory does not exist: {up_dir}")
    if not cv_dir.is_dir():
        raise ValueError(f"Converted directory does not exist: {cv_dir}")

    # Determine file pairing
    all_extensions = source_extensions + header_extensions
    if file_map_path:
        file_map = _load_file_map(Path(file_map_path).resolve())
        paired, unpaired_up, unpaired_cv = _pair_with_map(
            up_dir, cv_dir, file_map,
            upstream_extensions=all_extensions,
            converted_extensions=all_extensions,
        )
    else:
        paired, unpaired_up, unpaired_cv = _auto_pair_files(
            up_dir, cv_dir,
            upstream_extensions=all_extensions,
            converted_extensions=all_extensions,
        )

    # Filter to only score source files (not headers alone)
    source_paired = [(u, c) for u, c in paired if u.suffix in source_extensions]
    source_unpaired_up = [u for u in unpaired_up if u.suffix in source_extensions]

    # Score each paired source file
    per_file_reports: list[dict[str, Any]] = []
    for upstream_file, converted_file in source_paired:
        # Resolve headers in same directory for each file
        report = score_conversion(
            converted_source=converted_file,
            upstream_source=upstream_file,
            banned_symbols_file=banned_symbols_file,
            dt_binding_file=dt_binding_file,
        )
        per_file_reports.append({
            "upstream_file": str(upstream_file),
            "converted_file": str(converted_file),
            "status": "PAIRED",
            "upstream_lines": _file_line_count(upstream_file),
            "converted_lines": _file_line_count(converted_file),
            "categories": report["categories"],
            "overall": report["overall"],
        })

    # Add zero-score entries for unpaired upstream source files
    for upstream_file in source_unpaired_up:
        per_file_reports.append(_zero_score_report(upstream_file))

    # Compute weighted aggregate (weighted by upstream line count)
    total_upstream_lines = 0
    weighted_category_sums: dict[str, float] = {cat: 0.0 for cat in CATEGORY_ORDER}
    weighted_overall_sum = 0.0

    for file_report in per_file_reports:
        if file_report["status"] == "UNPAIRED":
            weight = file_report["line_count"]
        else:
            weight = file_report["upstream_lines"]
        total_upstream_lines += weight

        for cat_name in CATEGORY_ORDER:
            cat_score = float(file_report["categories"][cat_name]["score"])
            weighted_category_sums[cat_name] += cat_score * weight

        file_overall = float(file_report["overall"]["score"])
        weighted_overall_sum += file_overall * weight

    # Compute final aggregate
    aggregate_categories: dict[str, float] = {}
    for cat_name in CATEGORY_ORDER:
        if total_upstream_lines > 0:
            aggregate_categories[cat_name] = _round_score(
                weighted_category_sums[cat_name] / total_upstream_lines
            )
        else:
            aggregate_categories[cat_name] = 0.0

    if total_upstream_lines > 0:
        aggregate_overall = _round_score(weighted_overall_sum / total_upstream_lines)
    else:
        aggregate_overall = 0.0

    # Build final report
    scoring_sha = _scoring_logic_sha256()
    multifile_sha = hashlib.sha256(
        Path(__file__).read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()

    return {
        "scoring_engine": MULTIFILE_SCORING_ENGINE,
        "scoring_engine_version": MULTIFILE_SCORING_VERSION,
        "single_file_scorer_version": SCORING_ENGINE_VERSION,
        "inputs": {
            "upstream_dir": str(up_dir),
            "converted_dir": str(cv_dir),
            "file_map": str(file_map_path) if file_map_path else None,
            "banned_symbols_file": str(banned_symbols_file) if banned_symbols_file else None,
            "dt_binding_file": str(dt_binding_file) if dt_binding_file else None,
        },
        "file_pairing": {
            "paired_source_files": len(source_paired),
            "unpaired_upstream_source_files": len(source_unpaired_up),
            "unpaired_converted_files": len(unpaired_cv),
            "paired_header_files": len([(u, c) for u, c in paired if u.suffix in header_extensions]),
            "total_upstream_source_lines": total_upstream_lines,
            "pairing_details": [
                {"upstream": u.name, "converted": c.name}
                for u, c in source_paired
            ],
            "unpaired_upstream": [u.name for u in source_unpaired_up],
            "unpaired_converted": [f.name for f in unpaired_cv],
        },
        "per_file_scores": per_file_reports,
        "aggregate": {
            "method": "weighted_arithmetic_mean_by_upstream_line_count",
            "total_weight": total_upstream_lines,
            "categories": aggregate_categories,
            "overall": aggregate_overall,
        },
        "metadata": {
            "deterministic": True,
            "reproducible": True,
            "single_file_scoring_logic_sha256": scoring_sha,
            "multifile_scoring_logic_sha256": multifile_sha,
        },
    }


def render_multifile_score_json(report: dict[str, Any]) -> str:
    """Render deterministic JSON for a multi-file score report."""
    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-file deterministic conversion scoring (v4)"
    )
    parser.add_argument(
        "--upstream-dir", required=True,
        help="Directory containing upstream source files"
    )
    parser.add_argument(
        "--converted-dir", required=True,
        help="Directory containing converted source files"
    )
    parser.add_argument(
        "--file-map",
        help="Optional JSON file mapping upstream filenames to converted filenames"
    )
    parser.add_argument(
        "--banned-symbols",
        help="Optional path to banned symbols JSON"
    )
    parser.add_argument(
        "--dt-binding",
        help="Optional path to DT binding YAML"
    )
    parser.add_argument(
        "--source-extensions", nargs="*", default=[".c"],
        help="File extensions to treat as source (default: .c)"
    )
    parser.add_argument(
        "--header-extensions", nargs="*", default=[".h"],
        help="File extensions to treat as headers (default: .h)"
    )
    parser.add_argument(
        "--output",
        help="Optional path to write JSON output"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = score_multifile(
        upstream_dir=args.upstream_dir,
        converted_dir=args.converted_dir,
        file_map_path=args.file_map,
        banned_symbols_file=args.banned_symbols,
        dt_binding_file=args.dt_binding,
        source_extensions=tuple(args.source_extensions),
        header_extensions=tuple(args.header_extensions),
    )
    rendered = render_multifile_score_json(report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
