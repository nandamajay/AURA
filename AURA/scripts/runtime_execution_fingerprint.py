#!/usr/bin/env python3
"""Stamp transport artifacts with deterministic runtime execution fingerprints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_payload_hash(payload: dict[str, Any]) -> str:
    base = dict(payload)
    base.pop("deterministic_fingerprint", None)
    runtime_fp = base.get("runtime_execution_fingerprint")
    if isinstance(runtime_fp, dict):
        # Timestamp is intentionally runtime-volatile and must not affect
        # deterministic artifact identity used by replay drift detection.
        runtime_base = dict(runtime_fp)
        runtime_base.pop("timestamp", None)
        base["runtime_execution_fingerprint"] = runtime_base
    return _sha256_text(json.dumps(base, sort_keys=True, separators=(",", ":")))


def _run_cmd(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or proc.stderr or "").strip()


def _git_sha(repo_root: Path) -> str:
    code, out = _run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if code == 0 and out:
        return out
    return "unknown"


def _dependency_hashes(repo_root: Path) -> dict[str, str]:
    constraints = repo_root / "constraints" / "py312.txt"
    hashes: dict[str, str] = {}
    if constraints.exists():
        hashes["constraints_py312_sha256"] = _sha256_file(constraints)

    code, freeze = _run_cmd([sys.executable, "-m", "pip", "freeze"])
    if code == 0 and freeze:
        normalized = "\n".join(sorted(line.strip() for line in freeze.splitlines() if line.strip()))
        hashes["pip_freeze_sha256"] = _sha256_text(normalized)
    return hashes


def _runtime_execution_fingerprint(repo_root: Path) -> dict[str, Any]:
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    container_hash = os.environ.get("AURA_EXECUTION_CONTAINER_HASH", "").strip()
    if not container_hash:
        container_hash = _sha256_text(
            "|".join(
                [
                    platform.platform(),
                    sys.executable,
                    python_version,
                ]
            )
        )

    return {
        "python_version": python_version,
        "dependency_hashes": _dependency_hashes(repo_root),
        "git_sha": _git_sha(repo_root),
        "parser_version": "aura-runtime-parser-v1",
        "execution_container_hash": container_hash,
        "timestamp": _now_iso(),
    }


def _is_transport_contract_payload(payload: dict[str, Any]) -> bool:
    return bool(payload.get("report_name")) and bool(payload.get("schema_version"))


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run(output_dir: Path, repo_root: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_fp = _runtime_execution_fingerprint(repo_root)

    updated: list[dict[str, Any]] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    for path in sorted(output_dir.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            skipped.append(path.name)
            continue
        if not _is_transport_contract_payload(payload):
            skipped.append(path.name)
            continue
        try:
            payload["runtime_execution_fingerprint"] = execution_fp
            if not str(payload.get("deterministic_fingerprint", "")).strip():
                payload["deterministic_fingerprint"] = _canonical_payload_hash(payload)
            _write_json(path, payload)
            updated.append(
                {
                    "artifact": path.name,
                    "report_name": str(payload.get("report_name", "")),
                    "deterministic_fingerprint": str(payload.get("deterministic_fingerprint", "")),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            errors.append({"artifact": path.name, "error": str(exc)})

    status = "PASS" if updated and not errors else "FAIL_CLOSED"
    fail_closed_reasons: list[str] = []
    if not updated:
        fail_closed_reasons.append("no_transport_artifacts_stamped")
    if errors:
        fail_closed_reasons.append("artifact_fingerprint_stamping_failed")

    report = {
        "schema_version": "1.0",
        "report_name": "runtime_execution_fingerprint_report",
        "created_at": _now_iso(),
        "classification": status,
        "fail_closed_reasons": fail_closed_reasons,
        "runtime_execution_fingerprint": execution_fp,
        "updated_artifacts": updated,
        "skipped_files": skipped,
        "errors": errors,
    }
    report["deterministic_fingerprint"] = _canonical_payload_hash(report)

    report_path = output_dir / "runtime_execution_fingerprint_report.json"
    _write_json(report_path, report)
    return {
        "status": status,
        "report_path": str(report_path.resolve()),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "error_count": len(errors),
    }


def main() -> int:
    repo_root_default = Path(__file__).resolve().parents[1]
    output_dir_default = (repo_root_default.parent / "docs" / "operations" / "transport").resolve()
    parser = argparse.ArgumentParser(description="Stamp runtime execution fingerprints")
    parser.add_argument(
        "--output-dir",
        default=str(output_dir_default),
    )
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_default),
    )
    args = parser.parse_args()

    output = run(Path(args.output_dir), Path(args.repo_root))
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
