"""Deterministic serialization primitives for runtime cognition artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_DEFAULT_FLOAT_PRECISION = 6
_UUID_NAMESPACE = uuid.UUID("f2f6f8b9-fab4-4fd7-899f-0b21462b2cd1")


def _is_iso_timestamp(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False
    if "T" not in raw:
        return False
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def normalize_timestamp(value: str, *, precision: str = "milliseconds") -> str:
    """Normalize timestamp strings to UTC ISO format."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    utc = parsed.astimezone(timezone.utc)
    if precision == "seconds":
        utc = utc.replace(microsecond=0)
    elif precision == "milliseconds":
        ms = int(round(utc.microsecond / 1000.0))
        utc = utc.replace(microsecond=max(0, min(ms, 999)) * 1000)
    return utc.isoformat()


def normalize_path(path_like: str | os.PathLike[str], *, repo_root: str | Path | None = None) -> str:
    """Normalize filesystem paths for deterministic artifact payloads."""
    path = Path(path_like).expanduser().resolve()
    if repo_root is None:
        root = os.environ.get("AURA_REPO_ROOT", "").strip()
        if root:
            repo_root = Path(root).resolve()
    if repo_root is not None:
        try:
            rel = path.relative_to(Path(repo_root).resolve())
            return rel.as_posix()
        except Exception:
            pass
    return path.as_posix()


def deterministic_uuid(name: str, *, namespace: uuid.UUID = _UUID_NAMESPACE) -> str:
    """Generate deterministic UUIDv5 for stable lineage/cache keys."""
    return str(uuid.uuid5(namespace, str(name)))


def canonicalize(
    value: Any,
    *,
    float_precision: int = _DEFAULT_FLOAT_PRECISION,
    normalize_paths: bool = False,
    repo_root: str | Path | None = None,
) -> Any:
    """Recursively canonicalize values for deterministic hashing/serialization."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key in sorted(str(k) for k in value.keys()):
            out[key] = canonicalize(
                value[key],
                float_precision=float_precision,
                normalize_paths=normalize_paths,
                repo_root=repo_root,
            )
        return out

    if isinstance(value, list):
        return [
            canonicalize(
                item,
                float_precision=float_precision,
                normalize_paths=normalize_paths,
                repo_root=repo_root,
            )
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            canonicalize(
                item,
                float_precision=float_precision,
                normalize_paths=normalize_paths,
                repo_root=repo_root,
            )
            for item in value
        ]

    if isinstance(value, float):
        if not math.isfinite(value):
            return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
        return round(float(value), int(float_precision))

    if isinstance(value, Path):
        return normalize_path(value, repo_root=repo_root) if normalize_paths else value.as_posix()

    if isinstance(value, str):
        text = value.strip()
        if _is_iso_timestamp(text):
            return normalize_timestamp(text)
        if normalize_paths and ("/" in text or text.startswith(".")):
            try:
                return normalize_path(text, repo_root=repo_root)
            except Exception:
                return text
        return value

    return value


def canonical_json(
    payload: Mapping[str, Any] | dict[str, Any],
    *,
    float_precision: int = _DEFAULT_FLOAT_PRECISION,
    normalize_paths: bool = False,
    repo_root: str | Path | None = None,
) -> str:
    canonical = canonicalize(
        dict(payload),
        float_precision=float_precision,
        normalize_paths=normalize_paths,
        repo_root=repo_root,
    )
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_sha256(
    payload: Mapping[str, Any] | dict[str, Any],
    *,
    float_precision: int = _DEFAULT_FLOAT_PRECISION,
    normalize_paths: bool = False,
    repo_root: str | Path | None = None,
) -> str:
    return hashlib.sha256(
        canonical_json(
            payload,
            float_precision=float_precision,
            normalize_paths=normalize_paths,
            repo_root=repo_root,
        ).encode("utf-8")
    ).hexdigest()


def dump_canonical_json(
    path: str | Path,
    payload: Mapping[str, Any] | dict[str, Any],
    *,
    float_precision: int = _DEFAULT_FLOAT_PRECISION,
    normalize_paths: bool = False,
    repo_root: str | Path | None = None,
) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canonical = canonicalize(
        dict(payload),
        float_precision=float_precision,
        normalize_paths=normalize_paths,
        repo_root=repo_root,
    )
    out_path.write_text(
        json.dumps(canonical, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
