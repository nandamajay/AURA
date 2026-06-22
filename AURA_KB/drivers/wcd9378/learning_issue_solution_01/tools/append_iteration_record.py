#!/usr/bin/env python3
"""Append one validated iteration record to iteration_change_log.jsonl.

This tool enforces the required fields from iteration_record_schema.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _validate_record(record: dict[str, Any], required_fields: list[str]) -> None:
    missing = [key for key in required_fields if key not in record]
    if missing:
        raise ValueError(f"Record missing required fields: {', '.join(missing)}")


def main() -> int:
    here = Path(__file__).resolve().parent
    default_root = here.parent

    parser = argparse.ArgumentParser(
        description="Append a validated iteration record to JSONL log."
    )
    parser.add_argument(
        "--record-file",
        required=True,
        help="Path to input record JSON (single JSON object).",
    )
    parser.add_argument(
        "--log-file",
        default=str(default_root / "iteration_change_log.jsonl"),
        help="Target JSONL log path.",
    )
    parser.add_argument(
        "--schema-file",
        default=str(default_root / "iteration_record_schema.json"),
        help="Schema path providing required_fields.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and print canonical record without writing.",
    )
    args = parser.parse_args()

    record_path = Path(args.record_file).resolve()
    log_path = Path(args.log_file).resolve()
    schema_path = Path(args.schema_file).resolve()

    record = _load_json(record_path)
    schema = _load_json(schema_path)
    required_fields = schema.get("required_fields")
    if not isinstance(required_fields, list) or not all(
        isinstance(key, str) for key in required_fields
    ):
        raise ValueError("Schema required_fields must be a list of strings")

    _validate_record(record, required_fields)

    # Canonicalized JSON line for deterministic replay/compare.
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))

    if args.dry_run:
        print(canonical)
        return 0

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(canonical)
        f.write("\n")

    print(f"Appended record to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
