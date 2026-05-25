"""Runtime execution contract for container-authoritative deterministic runs."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aura_sdk.transport.deterministic_serialization import stable_sha256


_MIN_PYTHON = (3, 12, 0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_containerized() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    try:
        content = open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return False
    lowered = content.lower()
    return any(token in lowered for token in ("docker", "containerd", "kubepods", "podman"))


@dataclass(frozen=True)
class RuntimeExecutionContract:
    component: str
    python_version: str
    python_version_tuple: tuple[int, int, int]
    python_executable: str
    containerized: bool
    execution_container_hash: str
    contract_version: str
    classification: str
    fail_closed_reasons: list[str]
    generated_at: str

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "component": self.component,
            "python_version": self.python_version,
            "python_version_tuple": list(self.python_version_tuple),
            "python_executable": self.python_executable,
            "containerized": self.containerized,
            "execution_container_hash": self.execution_container_hash,
            "contract_version": self.contract_version,
            "classification": self.classification,
            "fail_closed_reasons": list(self.fail_closed_reasons),
            "generated_at": self.generated_at,
        }
        payload["deterministic_fingerprint"] = stable_sha256(
            {
                "component": payload["component"],
                "python_version": payload["python_version"],
                "python_version_tuple": payload["python_version_tuple"],
                "python_executable": payload["python_executable"],
                "containerized": payload["containerized"],
                "execution_container_hash": payload["execution_container_hash"],
                "contract_version": payload["contract_version"],
                "classification": payload["classification"],
                "fail_closed_reasons": payload["fail_closed_reasons"],
            }
        )
        return payload


def resolve_runtime_contract(component: str) -> RuntimeExecutionContract:
    py_tuple = tuple(int(v) for v in sys.version_info[:3])  # type: ignore[assignment]
    py_ver = ".".join(str(v) for v in py_tuple)
    container_hash = os.environ.get("AURA_EXECUTION_CONTAINER_HASH", "").strip()
    containerized = _is_containerized()
    fail_reasons: list[str] = []

    if py_tuple < _MIN_PYTHON:
        fail_reasons.append("python_version_below_3_12")
    if not containerized:
        fail_reasons.append("non_container_runtime_detected")
    if not container_hash:
        # For service containers not launched through aura_container_exec.sh.
        container_hash = stable_sha256(
            {
                "platform": platform.platform(),
                "python_executable": sys.executable,
                "python_version": py_ver,
                "containerized": containerized,
            }
        )

    return RuntimeExecutionContract(
        component=str(component),
        python_version=py_ver,
        python_version_tuple=py_tuple,
        python_executable=sys.executable,
        containerized=containerized,
        execution_container_hash=container_hash,
        contract_version="1.0",
        classification="FAIL_CLOSED" if fail_reasons else "PASS",
        fail_closed_reasons=fail_reasons,
        generated_at=_now_iso(),
    )


def enforce_runtime_contract(component: str) -> RuntimeExecutionContract:
    contract = resolve_runtime_contract(component)
    if contract.classification != "PASS":
        reasons = ",".join(contract.fail_closed_reasons) or "unknown_runtime_contract_failure"
        raise RuntimeError(
            f"{component}: deterministic runtime contract failed ({reasons}); "
            "run via scripts/aura_container_exec.sh with Python 3.12 container runtime."
        )
    return contract
