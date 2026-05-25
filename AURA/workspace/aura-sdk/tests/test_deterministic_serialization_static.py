from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.deterministic_serialization import (  # noqa: E402
    canonical_json,
    deterministic_uuid,
    normalize_timestamp,
    stable_sha256,
)


def test_canonical_hash_stable_with_key_order_and_float_rounding() -> None:
    a = {
        "b": 1.123456789,
        "a": {"z": 5, "x": [3, 2, 1]},
    }
    b = {
        "a": {"x": [3, 2, 1], "z": 5},
        "b": 1.1234567889,
    }
    assert stable_sha256(a) == stable_sha256(b)
    assert canonical_json(a) == canonical_json(b)


def test_timestamp_normalization_to_utc_milliseconds() -> None:
    ts = normalize_timestamp("2026-05-25T10:11:12.123456+05:30")
    assert ts.startswith("2026-05-25T04:41:12.123")
    assert ts.endswith("+00:00")


def test_deterministic_uuid_v5_stable() -> None:
    one = deterministic_uuid("runtime:lineage:test")
    two = deterministic_uuid("runtime:lineage:test")
    assert one == two
