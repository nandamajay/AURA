#!/usr/bin/env python3
"""AURA environment/replay/contract stabilization validator.

This script is intentionally fail-closed and writes validation artifacts under:
docs/operations/transport/
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


@dataclass
class CmdResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 240,
) -> CmdResult:
    start = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        return CmdResult(command, proc.returncode, proc.stdout, proc.stderr, duration)
    except FileNotFoundError as exc:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        return CmdResult(command, 127, "", str(exc), duration)
    except subprocess.TimeoutExpired as exc:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        return CmdResult(
            command,
            124,
            exc.stdout or "",
            (exc.stderr or "") + "\nTIMEOUT",
            duration,
        )


def status_for(ok: bool, blocked: bool = False) -> str:
    if blocked:
        return "BLOCKED_ENV"
    return "PASS" if ok else "FAIL"


def _python_version_tuple(raw: str) -> tuple[int, int, int]:
    text = raw.strip()
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, str(exc)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_constraints(constraints_path: Path) -> dict[str, str]:
    pinned: dict[str, str] = {}
    if not constraints_path.exists():
        return pinned
    for raw in constraints_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            continue
        package, version = line.split("==", 1)
        pinned[package.strip().lower()] = version.strip()
    return pinned


def detect_repo_paths() -> tuple[Path, Path]:
    aura_root = Path(__file__).resolve().parents[1]
    workspace_root = aura_root.parent
    return aura_root, workspace_root


def build_python_env(aura_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    py_path = [
        str(aura_root / "services" / "core" / "src"),
        str(aura_root / "workspace" / "aura-sdk" / "src"),
    ]
    existing = env.get("PYTHONPATH", "")
    if existing:
        py_path.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(py_path)
    return env


def validate_runtime_endpoint_registration(aura_root: Path) -> dict[str, Any]:
    main_path = aura_root / "services" / "core" / "src" / "core" / "main.py"
    runtime_router = aura_root / "services" / "core" / "src" / "core" / "routers" / "runtime.py"

    main_source = main_path.read_text(encoding="utf-8")
    runtime_source = runtime_router.read_text(encoding="utf-8")

    runtime_mounted = "/api/v1/runtime" in main_source and "runtime.router" in main_source
    tree = ast.parse(runtime_source)
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    routes.append(
                        {
                            "method": dec.func.attr.upper(),
                            "path": str(dec.args[0].value),
                            "handler": node.name,
                        }
                    )

    expected_paths = {
        "/artifacts/index",
        "/artifacts/read",
        "/governance/summary",
        "/topology",
        "/equivalence",
        "/confidence",
    }
    discovered_paths = {entry["path"] for entry in routes}

    return {
        "runtime_router_mounted": runtime_mounted,
        "runtime_route_count": len(routes),
        "routes": routes,
        "expected_paths_present": sorted(expected_paths.intersection(discovered_paths)),
        "missing_expected_paths": sorted(expected_paths - discovered_paths),
        "status": "PASS" if runtime_mounted and expected_paths.issubset(discovered_paths) else "FAIL",
    }


def validate_frontend_backend_contract_alignment(aura_root: Path) -> dict[str, Any]:
    config_path = aura_root / "dashboard" / "src" / "config.ts"
    main_path = aura_root / "services" / "core" / "src" / "core" / "main.py"
    router_dir = aura_root / "services" / "core" / "src" / "core" / "routers"

    config_source = config_path.read_text(encoding="utf-8")
    runtime_keys = [
        "runtimeArtifactsIndex",
        "runtimeArtifactsRead",
        "runtimeGovernanceSummary",
        "runtimeTopology",
        "runtimeEquivalence",
        "runtimeConfidence",
    ]

    key_to_path: dict[str, str] = {}
    for key in runtime_keys:
        match = re.search(rf"{key}: `\$\{{API_BASE\}}([^`]+)`", config_source)
        if match:
            key_to_path[key] = match.group(1)

    main_source = main_path.read_text(encoding="utf-8")
    prefixes = {
        match.group(1): match.group(2)
        for match in re.finditer(r'app\.include_router\((\w+)\.router,\s*prefix="([^"]+)"', main_source)
    }

    backend_paths: set[str] = set()
    for router_file in router_dir.glob("*.py"):
        if router_file.name == "__init__.py":
            continue
        prefix = prefixes.get(router_file.stem, "")
        tree = ast.parse(router_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and isinstance(dec.func.value, ast.Name)
                        and dec.func.value.id == "router"
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                    ):
                        backend_paths.add((prefix + str(dec.args[0].value)).replace("//", "/"))

    coverage: dict[str, dict[str, Any]] = {}
    all_ok = True
    for key, path in key_to_path.items():
        covered = path in backend_paths or any(
            bp.startswith(path.rstrip("/") + "/") for bp in backend_paths
        )
        coverage[key] = {"path": path, "covered": covered}
        all_ok = all_ok and covered

    return {
        "configured_runtime_endpoints": key_to_path,
        "coverage": coverage,
        "status": "PASS" if all_ok and len(key_to_path) == len(runtime_keys) else "FAIL",
    }


def python_import_probe(
    python_bin: str, modules: list[str], *, env: dict[str, str] | None = None
) -> dict[str, Any]:
    payload = (
        "import importlib,json;"
        f"mods={json.dumps(modules)};"
        "missing=[];"
        "ok=True;"
        "for m in mods:\n"
        "  try:\n"
        "    importlib.import_module(m)\n"
        "  except Exception as exc:\n"
        "    ok=False\n"
        "    missing.append({'module':m,'error':str(exc)})\n"
        "print(json.dumps({'ok':ok,'missing':missing}))"
    )
    result = run_cmd([python_bin, "-c", payload], env=env, timeout=120)
    parsed: dict[str, Any] = {"ok": False, "missing": [], "parse_error": ""}
    if result.ok:
        try:
            parsed = json.loads(result.stdout.strip() or "{}")
        except Exception as exc:  # pragma: no cover - defensive
            parsed = {"ok": False, "missing": [], "parse_error": str(exc)}
    return {
        "python_bin": python_bin,
        "result": result,
        "parsed": parsed,
    }


def write_report(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def probe_fastapi_startup(
    python_bin: str,
    *,
    env: dict[str, str] | None = None,
    port: int = 18780,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    command = [
        python_bin,
        "-m",
        "uvicorn",
        "core.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.Popen(
            command,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        return {
            "status": "FAIL",
            "started": False,
            "error": str(exc),
            "command": command,
        }

    ready_url = f"http://127.0.0.1:{port}/health/live"
    ready = False
    ready_error = ""
    try:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urlrequest.urlopen(ready_url, timeout=1.5) as response:
                    if response.status == 200:
                        ready = True
                        break
            except (urlerror.URLError, TimeoutError) as exc:
                ready_error = str(exc)
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

    stdout = ""
    stderr = ""
    if proc.stdout:
        stdout = proc.stdout.read()[-1200:]
    if proc.stderr:
        stderr = proc.stderr.read()[-1200:]

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    return {
        "status": "PASS" if ready else "FAIL",
        "started": proc.returncode in (None, 0) or ready,
        "ready_endpoint": ready_url,
        "ready": ready,
        "returncode": proc.returncode,
        "duration_seconds": duration,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "last_error": ready_error,
        "command": command,
    }


def run() -> int:
    aura_root, workspace_root = detect_repo_paths()
    transport_dir = workspace_root / "docs" / "operations" / "transport"
    transport_dir.mkdir(parents=True, exist_ok=True)

    python_env = build_python_env(aura_root)
    constraints_path = aura_root / "constraints" / "py312.txt"
    constraints = parse_constraints(constraints_path)

    required_runtime_packages = ["uvicorn", "python-jose", "passlib", "fastapi", "httpx"]
    artifact_names = [
        "runtime_equivalence_report.json",
        "hardware_truth_graph.json",
        "replay_consistency_report.json",
        "runtime_governance_decision.json",
        "transformation_confidence_report.json",
        "runtime_replay_registry.json",
        "deterministic_runtime_replay.json",
        "runtime_execution_fingerprint_report.json",
        "aura_governance_state.json",
    ]

    python_current = run_cmd([sys.executable, "--version"])
    python_current_text = python_current.stdout.strip() or python_current.stderr.strip()
    python_current_tuple = _python_version_tuple(python_current_text)
    python312_runtime = python_current_tuple >= (3, 12, 0)

    local_probe = python_import_probe(
        sys.executable,
        ["fastapi", "uvicorn", "jose", "passlib", "httpx"],
        env=python_env,
    )
    py312_probe: dict[str, Any] = {
        "skipped": False,
        "python_bin": sys.executable,
        "result": local_probe["result"],
        "parsed": local_probe["parsed"],
    }

    pip_check = run_cmd([sys.executable, "-m", "pip", "check"], timeout=180)
    core_import = run_cmd(
        [
            sys.executable,
            "-c",
            "from core.main import app; print('routes', len(app.routes))",
        ],
        env=python_env,
    )
    contract_import = run_cmd(
        [
            sys.executable,
            "-c",
            (
                "from core.contracts.transport_artifact_contracts import collect_runtime_artifacts; "
                "print('contracts', len(collect_runtime_artifacts(strict=True)))"
            ),
        ],
        env=python_env,
    )
    startup_probe = probe_fastapi_startup(
        sys.executable,
        env=python_env,
    )

    runtime_route_validation = validate_runtime_endpoint_registration(aura_root)
    frontend_backend_alignment = validate_frontend_backend_contract_alignment(aura_root)

    dashboard_npm_ls = run_cmd(["npm", "ls", "--depth=0"], cwd=aura_root / "dashboard", timeout=180)
    dashboard_build = run_cmd(["npm", "run", "build"], cwd=aura_root / "dashboard", timeout=420)
    fingerprint_stamping = run_cmd(
        [
            sys.executable,
            str(aura_root / "scripts" / "runtime_execution_fingerprint.py"),
            "--output-dir",
            str(transport_dir),
            "--repo-root",
            str(aura_root),
        ],
        env=python_env,
        timeout=180,
    )

    runtime_artifact_checks: dict[str, dict[str, Any]] = {}
    for name in artifact_names:
        path = transport_dir / name
        payload, error = read_json(path)
        runtime_artifact_checks[name] = {
            "exists": path.exists(),
            "json_valid": error is None,
            "error": error,
            "sha256": sha256_file(path) if path.exists() else "",
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "top_level_type": type(payload).__name__ if payload is not None else "",
        }

    replay_registry_payload = as_dict(read_json(transport_dir / "runtime_replay_registry.json")[0])
    replay_consistency_payload = as_dict(read_json(transport_dir / "replay_consistency_report.json")[0])
    deterministic_runtime_replay_payload = as_dict(
        read_json(transport_dir / "deterministic_runtime_replay.json")[0]
    )
    runtime_governance_payload = as_dict(read_json(transport_dir / "runtime_governance_decision.json")[0])
    runtime_equivalence_payload = as_dict(read_json(transport_dir / "runtime_equivalence_report.json")[0])

    replay_registry_summary = as_dict(replay_registry_payload.get("summary"))
    replay_consistency = as_dict(replay_consistency_payload.get("consistency"))
    governance_gate = as_dict(runtime_governance_payload.get("runtime_promotion_gate"))
    equivalence_summary = as_dict(runtime_equivalence_payload.get("summary"))

    replay_registry_validation = {
        "generated_at": now_iso(),
        "status": "PASS" if replay_registry_payload else "FAIL",
        "registry_exists": bool(replay_registry_payload),
        "history_count": replay_registry_summary.get("history_count", 0),
        "deterministic_ready": replay_registry_summary.get("deterministic_ready", False),
        "replay_drift": replay_registry_summary.get("replay_drift", True),
        "latest_lineage_id": as_dict(replay_registry_payload.get("latest_entry")).get("lineage_id", ""),
        "latest_session_id": as_dict(replay_registry_payload.get("latest_entry")).get("session_id", ""),
        "deterministic_fingerprint": replay_registry_payload.get("deterministic_fingerprint", ""),
    }

    drift_detected = bool(
        replay_consistency.get("replay_drift", True)
        or equivalence_summary.get("critical_divergence_count", 0) > 0
    )
    replay_drift_analysis = {
        "generated_at": now_iso(),
        "replay_drift_flag": replay_consistency.get("replay_drift", True),
        "deterministic_event_ordering": replay_consistency.get("deterministic_event_ordering", False),
        "runtime_equivalence_confidence": equivalence_summary.get("confidence_score", 0.0),
        "critical_divergence_count": equivalence_summary.get("critical_divergence_count", 0),
        "drift_risk_classification": "HIGH" if drift_detected else "LOW",
    }

    replay_integrity_report = {
        "generated_at": now_iso(),
        "status": "PASS"
        if replay_registry_validation["status"] == "PASS"
        and replay_consistency.get("deterministic_event_ordering", False)
        and not replay_consistency.get("replay_drift", True)
        else "FAIL",
        "registry": replay_registry_validation,
        "consistency": replay_consistency_payload,
        "runtime_replay_event_count": as_dict(
            deterministic_runtime_replay_payload.get("replay_signal")
        ).get("event_count", 0),
        "runtime_replay_fingerprint": as_dict(
            deterministic_runtime_replay_payload.get("replay_signal")
        ).get("fingerprint", ""),
        "artifact_mutation_risk": [
            {
                "artifact": name,
                "sha256": details["sha256"],
                "risk": "HIGH" if (not details["exists"] or not details["json_valid"]) else "LOW",
            }
            for name, details in runtime_artifact_checks.items()
            if ("replay" in name or "governance" in name)
        ],
    }

    governance_replay_consistency = {
        "generated_at": now_iso(),
        "status": "PASS"
        if runtime_governance_payload and replay_consistency_payload and replay_registry_payload
        else "FAIL",
        "governance_classification": runtime_governance_payload.get("classification", ""),
        "promotion_eligible": runtime_governance_payload.get("promotion_eligible", False),
        "runtime_sensitive_impact_count": governance_gate.get("runtime_sensitive_impact_count", 0),
        "replay_consistency_classification": replay_consistency_payload.get("classification", ""),
        "replay_drift": replay_consistency.get("replay_drift", True),
        "lineage_match": {
            "governance_lineage": runtime_governance_payload.get("lineage_id", ""),
            "replay_registry_lineage": replay_registry_payload.get("lineage_id", ""),
            "consistent": runtime_governance_payload.get("lineage_id", "")
            == replay_registry_payload.get("lineage_id", ""),
        },
    }

    contract_integrity: dict[str, Any] = {
        "generated_at": now_iso(),
        "status": "PASS",
        "artifacts": [],
    }
    schema_validation: dict[str, Any] = {
        "generated_at": now_iso(),
        "status": "PASS",
        "schema_versions": {},
        "incompatible_payloads": [],
    }

    try:
        sys.path.insert(0, str(aura_root / "services" / "core" / "src"))
        from core.contracts.transport_artifact_contracts import collect_runtime_artifacts

        parsed = collect_runtime_artifacts(strict=True)
        for item in parsed:
            issues = [
                {"code": issue.code, "severity": issue.severity, "message": issue.message}
                for issue in item.validation.issues
            ]
            contract_integrity["artifacts"].append(
                {
                    "artifact_type": item.metadata.artifact_type,
                    "valid": item.validation.valid,
                    "classification": item.metadata.classification,
                    "lineage_id": item.metadata.lineage_id,
                    "session_id": item.metadata.session_id,
                    "issue_count": len(issues),
                    "issues": issues,
                }
            )
            schema_validation["schema_versions"][item.metadata.artifact_type] = (
                item.metadata.schema_version
            )
            if not item.validation.valid:
                schema_validation["incompatible_payloads"].append(item.metadata.artifact_type)

        if any(not item["valid"] for item in contract_integrity["artifacts"]):
            contract_integrity["status"] = "FAIL"
            schema_validation["status"] = "FAIL"
    except Exception as exc:  # pragma: no cover - defensive
        contract_integrity["status"] = "FAIL"
        contract_integrity["error"] = str(exc)
        schema_validation["status"] = "FAIL"
        schema_validation["error"] = str(exc)

    frontend_contracts_path = aura_root / "dashboard" / "src" / "runtime" / "contracts.ts"
    backend_contracts_path = (
        aura_root
        / "services"
        / "core"
        / "src"
        / "core"
        / "contracts"
        / "transport_artifact_contracts.py"
    )

    frontend_contract_source = (
        frontend_contracts_path.read_text(encoding="utf-8")
        if frontend_contracts_path.exists()
        else ""
    )
    backend_contract_source = (
        backend_contracts_path.read_text(encoding="utf-8")
        if backend_contracts_path.exists()
        else ""
    )

    dto_alignment_report = {
        "generated_at": now_iso(),
        "status": "PASS",
        "frontend_contract_file": str(frontend_contracts_path),
        "backend_contract_file": str(backend_contracts_path),
        "checks": {
            "frontend_has_runtime_governance_summary": "RuntimeGovernanceSummaryResponse"
            in frontend_contract_source,
            "frontend_has_runtime_equivalence": "RuntimeEquivalenceResponse" in frontend_contract_source,
            "frontend_has_runtime_topology": "RuntimeTopologyResponse" in frontend_contract_source,
            "frontend_has_runtime_confidence": "RuntimeConfidenceResponse" in frontend_contract_source,
            "backend_has_runtime_governance_contract": "class RuntimeGovernanceDecisionReport"
            in backend_contract_source,
            "backend_has_runtime_equivalence_contract": "class RuntimeEquivalenceReport"
            in backend_contract_source,
            "backend_has_runtime_topology_contract": "class HardwareTruthGraphReport"
            in backend_contract_source,
            "backend_has_runtime_confidence_contract": "class TransformationConfidenceReport"
            in backend_contract_source,
        },
        "frontend_backend_endpoint_alignment": frontend_backend_alignment,
    }
    if (
        not all(dto_alignment_report["checks"].values())
        or frontend_backend_alignment["status"] != "PASS"
    ):
        dto_alignment_report["status"] = "FAIL"

    dependency_integrity_report = {
        "generated_at": now_iso(),
        "status": "PASS",
        "python_constraints_file": str(constraints_path),
        "constraints_present": constraints_path.exists(),
        "required_runtime_package_pins": {pkg: constraints.get(pkg, "") for pkg in required_runtime_packages},
        "missing_required_pins": [pkg for pkg in required_runtime_packages if pkg not in constraints],
        "pip_check": {
            "status": status_for(pip_check.ok),
            "returncode": pip_check.returncode,
            "stdout_tail": pip_check.stdout[-1200:],
            "stderr_tail": pip_check.stderr[-1200:],
        },
        "local_import_probe": {
            "status": status_for(bool(as_dict(local_probe.get("parsed")).get("ok", False))),
            "python": sys.executable,
            "missing": as_dict(local_probe.get("parsed")).get("missing", []),
            "stderr_tail": local_probe["result"].stderr[-1200:],
        },
        "py312_import_probe": {
            "status": status_for(bool(as_dict(py312_probe.get("parsed")).get("ok", False))),
            "python": str(py312_probe.get("python_bin", sys.executable)),
            "missing": as_dict(py312_probe.get("parsed")).get("missing", []),
            "stderr_tail": py312_probe.get("result", CmdResult([], 0, "", "", 0)).stderr[-1200:]
            if isinstance(py312_probe.get("result"), CmdResult)
            else "",
        },
        "frontend_npm_ls": {
            "status": status_for(dashboard_npm_ls.ok),
            "returncode": dashboard_npm_ls.returncode,
            "stdout_tail": dashboard_npm_ls.stdout[-1200:],
            "stderr_tail": dashboard_npm_ls.stderr[-1200:],
        },
        "runtime_fingerprint_stamping": {
            "status": status_for(fingerprint_stamping.ok),
            "returncode": fingerprint_stamping.returncode,
            "stdout_tail": fingerprint_stamping.stdout[-1200:],
            "stderr_tail": fingerprint_stamping.stderr[-1200:],
        },
    }
    if dependency_integrity_report["missing_required_pins"]:
        dependency_integrity_report["status"] = "FAIL"
    if not pip_check.ok or not dashboard_npm_ls.ok or not fingerprint_stamping.ok:
        dependency_integrity_report["status"] = "FAIL"

    backend_runtime_validation = {
        "generated_at": now_iso(),
        "status": "PASS",
        "python_current": python_current_text,
        "python312_runtime": python312_runtime,
        "fastapi_startup_probe": {
            "status": status_for(core_import.ok, blocked=(not python312_runtime)),
            "returncode": core_import.returncode,
            "stdout": core_import.stdout.strip(),
            "stderr": core_import.stderr.strip(),
        },
        "fastapi_live_probe": {
            "status": status_for(startup_probe["status"] == "PASS", blocked=(not python312_runtime)),
            "details": startup_probe,
        },
        "runtime_contract_import": {
            "status": status_for(contract_import.ok, blocked=(not python312_runtime)),
            "returncode": contract_import.returncode,
            "stdout": contract_import.stdout.strip(),
            "stderr": contract_import.stderr.strip(),
        },
        "runtime_endpoint_registration": runtime_route_validation,
        "runtime_artifact_access": runtime_artifact_checks,
        "replay_registry_accessible": runtime_artifact_checks.get("runtime_replay_registry.json", {}).get(
            "exists", False
        ),
        "governance_artifact_accessible": runtime_artifact_checks.get(
            "runtime_governance_decision.json", {}
        ).get("exists", False),
        "runtime_execution_fingerprint_accessible": runtime_artifact_checks.get(
            "runtime_execution_fingerprint_report.json", {}
        ).get("exists", False),
    }
    if not python312_runtime:
        backend_runtime_validation["status"] = "BLOCKED_ENV"
    elif (
        not core_import.ok
        or not contract_import.ok
        or runtime_route_validation["status"] != "PASS"
        or startup_probe["status"] != "PASS"
        or not backend_runtime_validation["replay_registry_accessible"]
        or not backend_runtime_validation["governance_artifact_accessible"]
        or not backend_runtime_validation["runtime_execution_fingerprint_accessible"]
    ):
        backend_runtime_validation["status"] = "FAIL"

    dashboard_runtime_validation = {
        "generated_at": now_iso(),
        "status": "PASS" if dashboard_build.ok else "FAIL",
        "build": {
            "returncode": dashboard_build.returncode,
            "stdout_tail": dashboard_build.stdout[-2400:],
            "stderr_tail": dashboard_build.stderr[-2400:],
        },
        "runtime_query_layer_present": (aura_root / "dashboard" / "src" / "runtime" / "useRuntimeQuery.ts").exists(),
        "runtime_contract_layer_present": frontend_contracts_path.exists(),
    }

    environment_validation_report = {
        "generated_at": now_iso(),
        "status": "PASS",
        "python": {
            "current": python_current_text,
            "runtime_python_version_tuple": list(python_current_tuple),
            "python312_runtime": python312_runtime,
            "requires_python": ">=3.12",
        },
        "backend_runtime_validation_status": backend_runtime_validation["status"],
        "dashboard_runtime_validation_status": dashboard_runtime_validation["status"],
        "dependency_integrity_status": dependency_integrity_report["status"],
        "runtime_contract_integrity_status": contract_integrity["status"],
        "replay_integrity_status": replay_integrity_report["status"],
        "blockers": [],
    }
    if not python312_runtime:
        environment_validation_report["blockers"].append("python3.12_not_available")
    if backend_runtime_validation["status"] in {"FAIL", "BLOCKED_ENV"}:
        environment_validation_report["blockers"].append("backend_runtime_not_ready")
    if dashboard_runtime_validation["status"] != "PASS":
        environment_validation_report["blockers"].append("dashboard_build_failed")
    if dependency_integrity_report["status"] != "PASS":
        environment_validation_report["blockers"].append("dependency_integrity_failed")
    if contract_integrity["status"] != "PASS":
        environment_validation_report["blockers"].append("runtime_contract_integrity_failed")
    if replay_integrity_report["status"] != "PASS":
        environment_validation_report["blockers"].append("replay_integrity_failed")
    if environment_validation_report["blockers"]:
        environment_validation_report["status"] = "FAIL"

    readiness_status = "READY" if environment_validation_report["status"] == "PASS" else "BLOCKED"
    blockers = environment_validation_report["blockers"]
    blocker_lines = "\n".join(f"- {entry}" for entry in blockers) if blockers else "- none"
    bootstrap_readiness_report = (
        "# AURA Bootstrap Readiness Report\n\n"
        f"Generated: {now_iso()}\n\n"
        f"- Readiness: **{readiness_status}**\n"
        f"- Environment status: `{environment_validation_report['status']}`\n"
        f"- Backend runtime: `{backend_runtime_validation['status']}`\n"
        f"- Dashboard runtime: `{dashboard_runtime_validation['status']}`\n"
        f"- Dependency integrity: `{dependency_integrity_report['status']}`\n"
        f"- Replay integrity: `{replay_integrity_report['status']}`\n"
        f"- Contract integrity: `{contract_integrity['status']}`\n\n"
        "## Blockers\n"
        f"{blocker_lines}\n\n"
        "## Replay Hardening\n"
        f"- Registry status: `{replay_registry_validation['status']}`\n"
        f"- Replay drift flag: `{replay_drift_analysis['replay_drift_flag']}`\n"
        f"- Deterministic ordering: `{replay_drift_analysis['deterministic_event_ordering']}`\n\n"
        "## Contract Hardening\n"
        f"- DTO alignment: `{dto_alignment_report['status']}`\n"
        f"- Transport schema validation: `{schema_validation['status']}`\n"
        f"- Runtime contract validation: `{contract_integrity['status']}`\n"
    )

    outputs = {
        "environment_validation_report.json": environment_validation_report,
        "backend_runtime_validation.json": backend_runtime_validation,
        "dashboard_runtime_validation.json": dashboard_runtime_validation,
        "dependency_integrity_report.json": dependency_integrity_report,
        "replay_integrity_report.json": replay_integrity_report,
        "replay_drift_analysis.json": replay_drift_analysis,
        "replay_registry_validation.json": replay_registry_validation,
        "governance_replay_consistency.json": governance_replay_consistency,
        "runtime_contract_integrity.json": contract_integrity,
        "dto_alignment_report.json": dto_alignment_report,
        "transport_schema_validation.json": schema_validation,
    }
    for name, payload in outputs.items():
        write_report(transport_dir / name, payload)
    (transport_dir / "bootstrap_readiness_report.md").write_text(
        bootstrap_readiness_report, encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "environment": environment_validation_report["status"],
                "backend": backend_runtime_validation["status"],
                "dashboard": dashboard_runtime_validation["status"],
                "dependency": dependency_integrity_report["status"],
                "replay": replay_integrity_report["status"],
                "contracts": contract_integrity["status"],
                "outputs_dir": str(transport_dir),
            },
            indent=2,
        )
    )

    return 0 if environment_validation_report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(run())
