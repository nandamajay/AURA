from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import aura_sdk.transport.runtime_execution_contract as rec  # noqa: E402


def test_runtime_execution_contract_detects_python312() -> None:
    contract = rec.resolve_runtime_contract("unit-test")
    assert contract.python_version_tuple >= (3, 12, 0)


def test_runtime_execution_contract_fail_closed_without_container(monkeypatch) -> None:
    monkeypatch.setattr(rec, "_is_containerized", lambda: False)
    contract = rec.resolve_runtime_contract("unit-test-non-container")
    assert contract.classification == "FAIL_CLOSED"
    assert "non_container_runtime_detected" in set(contract.fail_closed_reasons)
