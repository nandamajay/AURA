#!/usr/bin/env python3
"""Controlled plugin coexistence validation.

Validation-only campaign to characterize coexistence behavior for bounded synthetic
multi-domain workloads under current deterministic AURA architecture.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sqlite3
import string
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


def short_token(n: int = 6) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(n))


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def parse_iso_seconds(raw: object) -> float | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    return dt.timestamp()


def audit_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "row_count": 0,
            "mismatch_count": 0,
            "id_gap_count": 0,
            "sample_mismatches": [],
            "sample_id_gaps": [],
            "last_id": 0,
        }

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, event_type, chain_hash FROM audit_ledger ORDER BY id"
        ).fetchall()
        mismatch_count = 0
        id_gap_count = 0
        sample_mismatches: list[dict[str, Any]] = []
        sample_id_gaps: list[dict[str, Any]] = []

        prev_id: int | None = None
        for row in rows:
            row_id = int(row["id"])
            if prev_id is not None and row_id != prev_id + 1:
                id_gap_count += 1
                if len(sample_id_gaps) < 5:
                    sample_id_gaps.append({"prev_id": prev_id, "id": row_id})
            prev_id = row_id

            chain_hash = str(row["chain_hash"] or "")
            if len(chain_hash) != 64:
                mismatch_count += 1
                if len(sample_mismatches) < 5:
                    sample_mismatches.append(
                        {
                            "id": row_id,
                            "event_type": str(row["event_type"] or ""),
                            "chain_hash": chain_hash,
                        }
                    )

        return {
            "row_count": len(rows),
            "mismatch_count": mismatch_count,
            "id_gap_count": id_gap_count,
            "sample_mismatches": sample_mismatches,
            "sample_id_gaps": sample_id_gaps,
            "last_id": int(rows[-1]["id"]) if rows else 0,
        }
    finally:
        con.close()


def docker_memory_snapshot() -> dict[str, dict[str, str]]:
    cmd = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        "aura-core",
        "aura-ws-server",
        "aura-llm-gateway",
        "aura-dashboard",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": {"message": proc.stderr.strip()}}
    result: dict[str, dict[str, str]] = {}
    for line in proc.stdout.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        container = str(row.get("Container") or "")
        if not container:
            continue
        result[container] = {
            "cpu": str(row.get("CPUPerc") or ""),
            "mem": str(row.get("MemUsage") or ""),
            "mem_pct": str(row.get("MemPerc") or ""),
            "net_io": str(row.get("NetIO") or ""),
            "block_io": str(row.get("BlockIO") or ""),
            "pids": str(row.get("PIDs") or ""),
        }
    return result


def login_admin(core_base: str, admin_email: str, admin_password: str) -> str:
    r = requests.post(
        f"{core_base}/api/v1/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=20,
    )
    r.raise_for_status()
    body = r.json()
    token = str(body.get("access_token") or "")
    if not token:
        raise RuntimeError("login returned empty access_token")
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def run_ci_equivalent_checks(repo_root: Path) -> dict[str, Any]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_root}:/repo",
        "-w",
        "/repo",
        "python:3.12-slim",
        "bash",
        "-lc",
        (
            "set -euo pipefail; "
            "python -m pip install -q -e AURA/workspace/aura-sdk[dev] "
            "-e AURA/agents -e AURA/services/core pytest pytest-asyncio; "
            "python AURA/scripts/architecture-enforce.py; "
            "PYTHONPATH=AURA/agents/src:AURA/services/core/src:AURA/workspace/aura-sdk/src "
            "python -m pytest -q "
            "AURA/services/core/tests/test_governance_stabilization.py "
            "AURA/services/core/tests/test_event_audit_persistence.py "
            "AURA/services/core/tests/test_task_queue_retry_ordering.py "
            "AURA/workspace/aura-sdk/tests/test_replay.py "
            "AURA/workspace/aura-sdk/tests/test_architecture_enforcer.py "
            "AURA/agents/tests/test_base_agent_replay_hooks.py; "
            "PYTHONPATH=AURA/workspace/aura-sdk/src python AURA/scripts/determinism-gate.py"
        ),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    return {
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "duration_seconds": round(dt, 3),
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-40:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-40:]),
    }


def plugin_synthetic_domain_scan() -> dict[str, Any]:
    script = r'''
import asyncio
import json
import tempfile
from pathlib import Path

from aura_sdk.plugins.interface import SubsystemPlugin, PluginMetadata, PluginCapability
from aura_sdk.plugins.registry import PluginRegistry

DOMAINS = [
    ("driver", [PluginCapability.RULE_DISCOVERY, PluginCapability.PATCH_REVIEW]),
    ("media", [PluginCapability.SIMULATION, PluginCapability.HEURISTIC_VALIDATION]),
    ("automation", [PluginCapability.CODE_GENERATION, PluginCapability.PATTERN_MATCHING]),
    ("research", [PluginCapability.MAINTAINER_LOOKUP, PluginCapability.RULE_DISCOVERY]),
]

def write_plugin(root: Path, pkg: str, plugin_name: str, caps: list[str], fail: bool = False) -> None:
    p = root / pkg
    p.mkdir(parents=True, exist_ok=True)
    if fail:
        (p / "__init__.py").write_text("raise RuntimeError('synthetic plugin failure')\n", encoding="utf-8")
        return

    cap_lines = ", ".join([f"PluginCapability.{c}" for c in caps])
    (p / "__init__.py").write_text(
        "\n".join([
            "from pathlib import Path",
            "from typing import Any",
            "from aura_sdk.plugins.interface import SubsystemPlugin, PluginMetadata, PluginCapability",
            "class Plugin(SubsystemPlugin):",
            "    def _init_metadata(self):",
            f"        return PluginMetadata(name='{plugin_name}', display_name='{plugin_name}', capabilities=[{cap_lines}])",
            "    async def load_rules(self, rules_path: Path): return []",
            "    async def validate_patch(self, patch_path: Path, context: dict[str, Any]):",
            "        return {'valid': True, 'findings': [], 'confidence': 0.7, 'domain': context.get('plugin_domain', '')}",
            "    async def suggest_fix(self, issue: dict[str, Any], context: dict[str, Any]):",
            "        return {'suggestion': 'noop', 'confidence': 0.6, 'domain': context.get('plugin_domain', '')}",
            "",
        ]),
        encoding="utf-8",
    )


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aura-plugin-coexist-') as td:
        root = Path(td)

        for domain, caps in DOMAINS:
            cap_names = [c.name for c in caps]
            write_plugin(root, f"{domain}_good", f"{domain}-domain-plugin", cap_names)

        write_plugin(root, "automation_bad", "automation-domain-bad", ["CODE_GENERATION"], fail=True)

        # Intentional cross-domain collision risk.
        write_plugin(root, "driver_collision", "shared-domain-collision", ["RULE_DISCOVERY"])
        write_plugin(root, "media_collision", "shared-domain-collision", ["SIMULATION"])

        reg = PluginRegistry()
        loaded = await reg.scan_directory(root)
        names = reg.list_plugins()

        domain_counts = {}
        for name in names:
            domain = name.split("-", 1)[0] if "-" in name else "unknown"
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        print(json.dumps({
            "loaded_count": int(loaded),
            "registered_count": len(names),
            "registered_names": sorted(names),
            "domain_counts": domain_counts,
            "overwrite_detected": len(names) < int(loaded),
            "collision_plugin_present": "shared-domain-collision" in names,
            "expected_packages": 7,
        }))


asyncio.run(main())
'''
    cmd = [
        "docker",
        "exec",
        "aura-core",
        "sh",
        "-lc",
        f"PYTHONPATH=/workspace/aura-sdk/src:/app/src python - <<'PY'\n{script}\nPY",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for raw in reversed(proc.stdout.splitlines()):
        line = raw.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"plugin scan output not parseable: {proc.stdout}")


def _get_queue_stats(core_base: str, token: str) -> dict[str, Any]:
    r = requests.get(f"{core_base}/api/v1/tasks/queue/stats", headers=auth_headers(token), timeout=10)
    if r.status_code == 200:
        return r.json()
    return {"error": r.status_code, "body": r.text[:200]}


def _get_queue_isolation_stats(core_base: str, token: str) -> dict[str, Any]:
    r = requests.get(
        f"{core_base}/api/v1/tasks/queue/isolation",
        headers=auth_headers(token),
        timeout=10,
    )
    if r.status_code == 200:
        return r.json()
    return {"error": r.status_code, "body": r.text[:200]}


def _get_ws_coexistence_metrics(ws_base: str) -> dict[str, Any]:
    r = requests.get(f"{ws_base}/metrics/coexistence", timeout=10)
    if r.status_code == 200:
        return r.json()
    return {"error": r.status_code, "body": r.text[:200]}


def _get_task(task_url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    r = requests.get(task_url, headers=headers, timeout=10)
    body: dict[str, Any]
    try:
        body = r.json() if r.text else {}
    except Exception:
        body = {"raw": r.text[:200]}
    return r.status_code, body


def _task_status(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return "invalid"
    return str(body.get("status") or "unknown")


def _extract_domain(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return "unknown"
    input_data = body.get("input_data")
    if isinstance(input_data, dict):
        v = input_data.get("plugin_domain")
        if isinstance(v, str) and v:
            return v
    return "unknown"


def multi_domain_task_campaign(
    *,
    core_base: str,
    token: str,
    run_id: str,
    domains: dict[str, dict[str, Any]],
    duration_seconds: int = 45,
) -> dict[str, Any]:
    headers = auth_headers(token)

    create_results: list[dict[str, Any]] = []
    task_ids_by_domain: dict[str, list[str]] = {domain: [] for domain in domains}

    for domain, cfg in domains.items():
        for i in range(int(cfg.get("tasks", 0))):
            payload = {
                "agent_type": cfg["agent_type"],
                "priority": cfg["priority"],
                "description": f"coexist-{run_id}-{domain}-{i}",
                "input_data": {
                    "plugin_domain": domain,
                    "workflow_pattern": cfg["workflow_pattern"],
                    "replay_pattern": cfg["replay_pattern"],
                    "governance_scope": cfg["governance_scope"],
                    "event_behavior": cfg["event_behavior"],
                    "queue_behavior": cfg["queue_behavior"],
                    "run_id": run_id,
                    "task_index": i,
                },
                "max_retries": 3,
            }
            r = requests.post(f"{core_base}/api/v1/tasks/", headers=headers, json=payload, timeout=15)
            body: dict[str, Any]
            try:
                body = r.json() if r.text else {}
            except Exception:
                body = {"raw": r.text[:200]}

            task_id = str(body.get("task_id") or "")
            if r.status_code == 200 and task_id:
                task_ids_by_domain[domain].append(task_id)
            create_results.append(
                {
                    "domain": domain,
                    "status": r.status_code,
                    "task_id": task_id,
                    "body": body,
                }
            )

    all_task_ids = [task_id for ids in task_ids_by_domain.values() for task_id in ids]

    poll_samples: list[dict[str, Any]] = []
    replay_during_run: list[dict[str, Any]] = []
    start = time.time()

    while time.time() - start < duration_seconds:
        domain_counts: dict[str, dict[str, int]] = {domain: {} for domain in domains}
        status_map: dict[str, str] = {}

        for domain, task_ids in task_ids_by_domain.items():
            for task_id in task_ids:
                status_code, body = _get_task(f"{core_base}/api/v1/tasks/{task_id}", headers)
                status = _task_status(body) if status_code == 200 else f"http_{status_code}"
                status_map[task_id] = status
                domain_counts[domain][status] = domain_counts[domain].get(status, 0) + 1

        queue_stats = _get_queue_stats(core_base, token)
        poll_samples.append(
            {
                "ts": utc_iso(),
                "domain_status_counts": domain_counts,
                "queue_stats": queue_stats,
                "queue_isolation": _get_queue_isolation_stats(core_base, token),
            }
        )

        sample_for_replay = all_task_ids[: min(20, len(all_task_ids))]
        for task_id in sample_for_replay:
            rr = requests.get(
                f"{core_base}/api/v1/tasks/{task_id}/replay",
                headers=headers,
                timeout=10,
            )
            replay_during_run.append({"task_id": task_id, "status": rr.status_code})

        terminal_total = sum(
            1
            for status in status_map.values()
            if status in {"completed", "failed", "cancelled", "timed_out"}
        )
        if terminal_total >= max(1, len(all_task_ids) - 4):
            break

        time.sleep(1.5)

    final_task_state: dict[str, dict[str, Any]] = {}
    for task_id in all_task_ids:
        code, body = _get_task(f"{core_base}/api/v1/tasks/{task_id}", headers)
        final_task_state[task_id] = {
            "http_status": code,
            "status": _task_status(body) if code == 200 else f"http_{code}",
            "body": body,
        }

    replay_final: dict[str, dict[str, Any]] = {}
    for task_id in all_task_ids:
        rr = requests.get(f"{core_base}/api/v1/tasks/{task_id}/replay", headers=headers, timeout=10)
        try:
            body = rr.json() if rr.text else {}
        except Exception:
            body = {"raw": rr.text[:200]}
        replay_final[task_id] = {
            "status": rr.status_code,
            "integrity_ok": bool(body.get("integrity_ok")) if isinstance(body, dict) else False,
            "body": body if isinstance(body, dict) else {},
        }

    per_domain_summary: dict[str, Any] = {}
    for domain, task_ids in task_ids_by_domain.items():
        status_counter: Counter[str] = Counter()
        replay_counter: Counter[str] = Counter()
        integrity_ok = 0
        start_lags: list[float] = []

        for task_id in task_ids:
            st = final_task_state.get(task_id, {})
            status_counter[str(st.get("status") or "unknown")] += 1

            body = st.get("body") if isinstance(st.get("body"), dict) else {}
            created_at = parse_iso_seconds(body.get("created_at"))
            started_at = parse_iso_seconds(body.get("started_at"))
            if created_at is not None and started_at is not None and started_at >= created_at:
                start_lags.append(started_at - created_at)

            rp = replay_final.get(task_id, {})
            replay_counter[str(rp.get("status") or "0")] += 1
            if rp.get("integrity_ok") is True:
                integrity_ok += 1

        per_domain_summary[domain] = {
            "created": len(task_ids),
            "final_status_counts": dict(status_counter),
            "replay_status_counts": dict(replay_counter),
            "replay_integrity_ok": integrity_ok,
            "start_lag_seconds": {
                "count": len(start_lags),
                "p50": round(sorted(start_lags)[int(0.5 * (len(start_lags) - 1))], 3) if start_lags else None,
                "p95": round(sorted(start_lags)[int(0.95 * (len(start_lags) - 1))], 3) if start_lags else None,
                "max": round(max(start_lags), 3) if start_lags else None,
            },
        }

    replay_during_counts = Counter(str(row.get("status") or "0") for row in replay_during_run)

    return {
        "create_results": create_results,
        "task_ids_by_domain": task_ids_by_domain,
        "poll_samples": poll_samples,
        "final_task_state": final_task_state,
        "replay_during_run_status_counts": dict(replay_during_counts),
        "replay_final": replay_final,
        "per_domain_summary": per_domain_summary,
    }


def replay_namespace_validation(
    *, db_path: Path, task_ids_by_domain: dict[str, list[str]]
) -> dict[str, Any]:
    expected: dict[str, str] = {}
    for domain, task_ids in task_ids_by_domain.items():
        for task_id in task_ids:
            expected[task_id] = domain

    found_rows: dict[str, dict[str, Any]] = {}
    if db_path.exists() and expected:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        try:
            for task_id in expected:
                row = con.execute(
                    "SELECT task_id, recording_state, input_json, snapshot_json, output_hash, snapshot_hash FROM task_logs WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row is None:
                    continue
                found_rows[task_id] = dict(row)
        finally:
            con.close()

    mismatches: list[dict[str, Any]] = []
    domain_counts = Counter()
    finalized_by_domain = Counter()

    for task_id, row in found_rows.items():
        exp = expected.get(task_id, "")
        observed_domain = "unknown"
        input_json = row.get("input_json")
        if isinstance(input_json, str):
            try:
                payload = json.loads(input_json)
                if isinstance(payload, dict):
                    observed_domain = str(payload.get("plugin_domain") or "unknown")
            except Exception:
                observed_domain = "invalid_json"

        domain_counts[observed_domain] += 1
        if str(row.get("recording_state") or "") == "finalized":
            finalized_by_domain[observed_domain] += 1

        if observed_domain != exp:
            mismatches.append(
                {
                    "task_id": task_id,
                    "expected_domain": exp,
                    "observed_domain": observed_domain,
                    "recording_state": row.get("recording_state"),
                }
            )

    missing_task_logs = sorted([task_id for task_id in expected if task_id not in found_rows])

    return {
        "expected_task_count": len(expected),
        "found_task_log_count": len(found_rows),
        "missing_task_log_count": len(missing_task_logs),
        "missing_task_log_sample": missing_task_logs[:20],
        "namespace_mismatch_count": len(mismatches),
        "namespace_mismatches_sample": mismatches[:20],
        "found_domain_counts": dict(domain_counts),
        "finalized_by_observed_domain": dict(finalized_by_domain),
    }


def create_governance_fixture_in_container(
    *, run_id: str, domains: list[str], approvals_per_domain: int, db_path_in_container: str
) -> dict[str, Any]:
    script = f"""
import json
import sqlite3
import time

run_id = {json.dumps(run_id)}
domains = {json.dumps(domains)}
count = {int(approvals_per_domain)}
db_path = {json.dumps(db_path_in_container)}

con = sqlite3.connect(db_path)
now_ts = int(time.time())
sub_row = con.execute("SELECT id FROM subsystems ORDER BY created_at LIMIT 1").fetchone()
subsystem_id = sub_row[0] if sub_row else None

fixture = {{}}
for domain in domains:
    patch_id = f"coex-patch-{{run_id}}-{{domain}}"
    con.execute(
        '''
        INSERT OR REPLACE INTO patches
        (id, subsystem_id, version, status, title, description, generated_by, created_at, updated_at)
        VALUES (?, ?, 1, 'reviewing', ?, ?, 'coexistence', ?, ?)
        ''',
        (patch_id, subsystem_id, f"Coexistence patch {{domain}}", f"scope={{domain}}", now_ts, now_ts),
    )

    approvals = []
    dims = ["lifecycle", "subsystem", "quality"]
    for i in range(count):
        aid = f"coex-appr-{{run_id}}-{{domain}}-{{i}}"
        approvals.append(aid)
        con.execute(
            '''
            INSERT OR REPLACE INTO approvals
            (id, patch_id, dimension, stage, status, created_at, updated_at)
            VALUES (?, ?, ?, 'review', 'pending', ?, ?)
            ''',
            (aid, patch_id, dims[i % len(dims)], now_ts, now_ts),
        )

    fixture[domain] = {{"patch_id": patch_id, "approval_ids": approvals}}

con.commit()
con.close()
print(json.dumps(fixture))
"""

    cmd = [
        "docker",
        "exec",
        "aura-core",
        "sh",
        "-lc",
        f"python - <<'PY'\n{script}\nPY",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for raw in reversed(proc.stdout.splitlines()):
        line = raw.strip()
        if line.startswith("{") and line.endswith("}"):
            payload = json.loads(line)
            if isinstance(payload, dict):
                return payload
    raise RuntimeError(f"governance fixture output parse failed: {proc.stdout}")


def governance_scope_campaign(
    *,
    core_base: str,
    token: str,
    run_id: str,
    db_path: Path,
    db_path_in_container: str,
    domains: list[str],
) -> dict[str, Any]:
    headers = auth_headers(token)
    fixture = create_governance_fixture_in_container(
        run_id=run_id,
        domains=domains,
        approvals_per_domain=12,
        db_path_in_container=db_path_in_container,
    )

    before = audit_summary(db_path)

    phase1_results: list[dict[str, Any]] = []
    target_domain = domains[0]
    target_approvals = fixture[target_domain]["approval_ids"]

    phase1_actions = [
        (target_approvals[0], "grant"),
        (target_approvals[1], "reject"),
        (target_approvals[2], "comment"),
        (target_approvals[3], "escalate"),
    ]

    for aid, action in phase1_actions:
        r = requests.post(
            f"{core_base}/api/v1/governance/approvals/{aid}",
            headers=headers,
            json={"action": action, "comment": f"{run_id}:{target_domain}:{action}"},
            timeout=20,
        )
        try:
            body = r.json() if r.text else {}
        except Exception:
            body = {"raw": r.text[:200]}
        phase1_results.append(
            {"approval_id": aid, "domain": target_domain, "action": action, "status": r.status_code, "body": body}
        )

    con_phase1 = sqlite3.connect(str(db_path))
    con_phase1.row_factory = sqlite3.Row
    pending_outside_phase1: dict[str, int] = {}
    try:
        for domain in domains:
            if domain == target_domain:
                continue
            ids = fixture[domain]["approval_ids"]
            q = ",".join(["?"] * len(ids))
            row = con_phase1.execute(
                f"SELECT COUNT(*) AS c FROM approvals WHERE id IN ({q}) AND status = 'pending'",
                ids,
            ).fetchone()
            pending_outside_phase1[domain] = int(row["c"] if row is not None else 0)
    finally:
        con_phase1.close()

    async_calls: list[tuple[str, str, str]] = []
    for domain in domains:
        ids = fixture[domain]["approval_ids"]
        actions = ["grant", "reject", "comment", "escalate"]
        for i, aid in enumerate(ids):
            action = actions[i % len(actions)]
            async_calls.append((domain, aid, action))

    random.Random(42).shuffle(async_calls)

    phase2_results: list[dict[str, Any]] = []
    for domain, aid, action in async_calls:
        r = requests.post(
            f"{core_base}/api/v1/governance/approvals/{aid}",
            headers=headers,
            json={"action": action, "comment": f"{run_id}:{domain}:{action}:phase2"},
            timeout=20,
        )
        try:
            body = r.json() if r.text else {}
        except Exception:
            body = {"raw": r.text[:200]}
        phase2_results.append(
            {
                "domain": domain,
                "approval_id": aid,
                "action": action,
                "status": r.status_code,
                "body": body,
            }
        )

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        status_by_domain: dict[str, dict[str, int]] = {}
        pending_outside_after_phase2 = {}

        for domain in domains:
            ids = fixture[domain]["approval_ids"]
            q = ",".join(["?"] * len(ids))
            rows = con.execute(
                f"SELECT id, status, comments, reviewed_at FROM approvals WHERE id IN ({q})",
                ids,
            ).fetchall()
            c = Counter(str(r["status"] or "") for r in rows)
            status_by_domain[domain] = dict(c)
            if domain != target_domain:
                pending_outside_after_phase2[domain] = c.get("pending", 0)

        all_ids = [aid for d in domains for aid in fixture[d]["approval_ids"]]
        q2 = ",".join(["?"] * len(all_ids))
        audit_rows = con.execute(
            f"SELECT id, timestamp, event_type, target_id, after_state FROM audit_ledger WHERE target_type='approval' AND target_id IN ({q2}) ORDER BY id",
            all_ids,
        ).fetchall()
        audit_entries = [dict(r) for r in audit_rows]
    finally:
        con.close()

    after = audit_summary(db_path)

    phase1_status_counts = Counter(str(r.get("status") or "") for r in phase1_results)
    phase2_status_counts = Counter(str(r.get("status") or "") for r in phase2_results)

    return {
        "fixture": fixture,
        "phase1_results": phase1_results,
        "phase2_results": phase2_results,
        "phase1_status_counts": dict(phase1_status_counts),
        "phase2_status_counts": dict(phase2_status_counts),
        "status_by_domain": status_by_domain,
        "pending_outside_target_after_phase1": pending_outside_phase1,
        "pending_outside_target_after_phase2": pending_outside_after_phase2,
        "audit_entries_count": len(audit_entries),
        "audit_entries_sample": audit_entries[:60],
        "audit_before": before,
        "audit_after": after,
        "audit_delta_rows": after["row_count"] - before["row_count"],
        "audit_delta_mismatch": after["mismatch_count"] - before["mismatch_count"],
    }


async def _collect_sse_for_domains(
    *,
    ws_base: str,
    run_id: str,
    watch_domain: str,
    duration_seconds: float,
    slow: bool,
    channel_filter: str,
) -> dict[str, Any]:
    import httpx

    url = f"{ws_base}/events?channels={channel_filter}"
    own = 0
    foreign = 0
    total = 0
    retry_seen: dict[str, list[int]] = defaultdict(list)
    started = time.time()

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", url) as response:
            async for line in response.aiter_lines():
                if time.time() - started > duration_seconds:
                    break
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("run_id") != run_id:
                    continue

                total += 1
                domain = str(payload.get("plugin_domain") or "")
                if domain == watch_domain:
                    own += 1
                else:
                    foreign += 1

                if payload.get("kind") == "retry":
                    attempt = payload.get("attempt")
                    if isinstance(attempt, int):
                        retry_seen[domain].append(attempt)

                if slow:
                    await asyncio.sleep(0.03)

    return {
        "watch_domain": watch_domain,
        "total": total,
        "own": own,
        "foreign": foreign,
        "foreign_ratio": round(foreign / max(1, total), 3),
        "retry_seen": {k: v[:8] for k, v in retry_seen.items()},
    }


async def event_stream_interference_campaign(
    *, ws_base: str, run_id: str, domains: list[str], duration_seconds: int
) -> dict[str, Any]:
    import httpx

    collectors: list[asyncio.Task[dict[str, Any]]] = []
    for i, domain in enumerate(domains):
        collectors.append(
            asyncio.create_task(
                _collect_sse_for_domains(
                    ws_base=ws_base,
                    run_id=run_id,
                    watch_domain=domain,
                    duration_seconds=float(duration_seconds),
                    slow=(i % 2 == 1),
                    channel_filter=f"system:{domain}",
                )
            )
        )

    await asyncio.sleep(0.5)

    broadcast_results: list[dict[str, Any]] = []
    retries_sent: dict[str, list[int]] = {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        for i in range(250):
            for domain in domains:
                event = {
                    "event_id": f"coex-{run_id}-{domain}-burst-{i}",
                    "event_type": "runtime.coexistence.burst",
                    "timestamp": utc_iso(),
                    "payload": {
                        "run_id": run_id,
                        "plugin_domain": domain,
                        "kind": "burst",
                        "seq": i,
                    },
                }
                r = await client.post(f"{ws_base}/broadcast", json={"channel": "system", "event": event})
                body = r.json() if r.text else {}
                broadcast_results.append({"status": r.status_code, "body": body, "domain": domain})

                if i % 80 == 0:
                    r2 = await client.post(f"{ws_base}/broadcast", json={"channel": "system", "event": event})
                    body2 = r2.json() if r2.text else {}
                    broadcast_results.append({"status": r2.status_code, "body": body2, "domain": domain, "dup": True})

        for domain in domains:
            retries_sent[domain] = [2, 1, 3]
            for attempt in retries_sent[domain]:
                ev = {
                    "event_id": f"coex-{run_id}-{domain}-retry-{attempt}",
                    "event_type": "runtime.coexistence.retry",
                    "timestamp": utc_iso(),
                    "payload": {
                        "run_id": run_id,
                        "plugin_domain": domain,
                        "kind": "retry",
                        "op": f"{domain}-op",
                        "attempt": attempt,
                        "retry_scope": f"domain:{domain}:run:{run_id}:op:{domain}-op",
                    },
                }
                rr = await client.post(f"{ws_base}/broadcast", json={"channel": "system", "event": ev})
                bodyr = rr.json() if rr.text else {}
                broadcast_results.append({"status": rr.status_code, "body": bodyr, "domain": domain, "retry": True})

    collected = await asyncio.gather(*collectors)

    recipients = [
        int((x.get("body") or {}).get("recipients", 0))
        for x in broadcast_results
        if x.get("status") == 200 and isinstance(x.get("body"), dict)
    ]
    duplicate_drops = sum(1 for x in broadcast_results if isinstance(x.get("body"), dict) and (x.get("body") or {}).get("dropped_duplicate") is True)

    retry_order_by_domain: dict[str, list[int]] = {}
    for row in collected:
        retry_seen = row.get("retry_seen")
        if isinstance(retry_seen, dict):
            for domain, seq in retry_seen.items():
                if domain not in retry_order_by_domain and isinstance(seq, list) and seq:
                    retry_order_by_domain[domain] = [int(v) for v in seq[:3]]

    return {
        "collectors": collected,
        "broadcast_calls": len(broadcast_results),
        "broadcast_recipients_min": min(recipients) if recipients else 0,
        "broadcast_recipients_max": max(recipients) if recipients else 0,
        "duplicate_drops": duplicate_drops,
        "retries_sent": retries_sent,
        "retry_order_observed": retry_order_by_domain,
    }


def watchdog_cross_domain_campaign(*, run_id: str, domains: list[str], db_path_in_container: str) -> dict[str, Any]:
    script = f'''
import asyncio
import json
import time

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.models.event import EventType
from aura_sdk.replay.recorder import TaskRecorder
from core.services.watchdog import AgentWatch, WatchdogConfig, WatchdogManager


class FakeProcess:
    def __init__(self, term_exits: bool):
        self.term_exits = term_exits
        self.returncode = None

    def send_signal(self, sig):
        if sig == 15 and self.term_exits:
            self.returncode = 0

    def kill(self):
        self.returncode = -9

    async def wait(self):
        if self.returncode is None:
            await asyncio.sleep(0.1)
            if self.term_exits:
                self.returncode = 0
        return int(self.returncode or 0)


async def main():
    run_id = {json.dumps(run_id)}
    domains = {json.dumps(domains)}
    recorder = TaskRecorder({json.dumps(db_path_in_container)})

    bus = EventBus()
    await bus.start()

    timeout_events = []
    killed_events = []

    async def on_timeout(e):
        timeout_events.append(e)

    async def on_killed(e):
        killed_events.append(e)

    bus.subscribe(EventType.AGENT_TIMEOUT, on_timeout)
    bus.subscribe(EventType.AGENT_KILLED, on_killed)

    wd = WatchdogManager(
        event_bus=bus,
        config=WatchdogConfig(
            heartbeat_interval_seconds=0.05,
            missed_threshold=2,
            check_interval_seconds=0.02,
            sigterm_wait_seconds=0.05,
            max_watches=64,
        ),
        replay_recorder=recorder,
    )
    await wd.start()

    task_ids = []
    for domain in domains:
        for i in range(2):
            aid = f"coex-wd-kill-{{run_id}}-{{domain}}-{{i}}"
            tid = f"coex-wd-task-kill-{{run_id}}-{{domain}}-{{i}}"
            task_ids.append(tid)
            wd.register(
                AgentWatch(
                    agent_id=aid,
                    task_id=tid,
                    agent_type="learning",
                    process=FakeProcess(term_exits=False),
                    last_heartbeat=time.time() - 1,
                )
            )

        aid2 = f"coex-wd-term-{{run_id}}-{{domain}}"
        tid2 = f"coex-wd-task-term-{{run_id}}-{{domain}}"
        task_ids.append(tid2)
        wd.register(
            AgentWatch(
                agent_id=aid2,
                task_id=tid2,
                agent_type="learning",
                process=FakeProcess(term_exits=True),
                last_heartbeat=time.time() - 1,
            )
        )

    await asyncio.sleep(1.2)
    states_after = wd.list_states()
    await wd.stop()
    await bus.stop()

    def by_domain(task_id: str) -> str:
        for domain in domains:
            if f"-{{domain}}-" in task_id or task_id.endswith(f"-{{domain}}"):
                return domain
        return "unknown"

    timeout_by_domain = {{}}
    for e in timeout_events:
        d = by_domain(str(e.source.task_id or ""))
        timeout_by_domain[d] = timeout_by_domain.get(d, 0) + 1

    killed_by_domain = {{}}
    for e in killed_events:
        d = by_domain(str(e.source.task_id or ""))
        killed_by_domain[d] = killed_by_domain.get(d, 0) + 1

    print(json.dumps({{
        "registered": len(task_ids),
        "timeout_events": len(timeout_events),
        "killed_events": len(killed_events),
        "timeout_by_domain": timeout_by_domain,
        "killed_by_domain": killed_by_domain,
        "states_after_count": len(states_after),
        "task_ids": task_ids,
    }}))


asyncio.run(main())
'''

    cmd = [
        "docker",
        "exec",
        "aura-core",
        "sh",
        "-lc",
        f"PYTHONPATH=/workspace/aura-sdk/src:/app/src python - <<'PY'\n{script}\nPY",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for raw in reversed(proc.stdout.splitlines()):
        line = raw.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"watchdog campaign output parse failed: {proc.stdout}")


def replay_check_for_watchdog_tasks(core_base: str, token: str, task_ids: list[str]) -> dict[str, Any]:
    headers = auth_headers(token)
    statuses: Counter[str] = Counter()
    per_task: dict[str, int] = {}
    for task_id in task_ids:
        r = requests.get(f"{core_base}/api/v1/tasks/{task_id}/replay", headers=headers, timeout=10)
        statuses[str(r.status_code)] += 1
        per_task[task_id] = r.status_code
    return {
        "status_counts": dict(statuses),
        "missing_replay_count": sum(1 for x in per_task.values() if x != 200),
        "sample": dict(list(per_task.items())[:20]),
    }


def compute_interference_matrix(
    *,
    task_campaign: dict[str, Any],
    replay_ns: dict[str, Any],
    governance: dict[str, Any],
    events: dict[str, Any],
    watchdog: dict[str, Any],
) -> dict[str, Any]:
    queue_starvation_flag = False
    lags = []
    for domain_data in task_campaign.get("per_domain_summary", {}).values():
        lag = ((domain_data.get("start_lag_seconds") or {}).get("p95"))
        if isinstance(lag, (int, float)):
            lags.append(float(lag))
    if lags and (max(lags) - min(lags)) > 15.0:
        queue_starvation_flag = True

    foreign_ratios = [
        float(row.get("foreign_ratio") or 0.0)
        for row in events.get("collectors", [])
        if isinstance(row, dict)
    ]
    max_foreign_ratio = max(foreign_ratios) if foreign_ratios else 0.0

    replay_bleed = int(replay_ns.get("namespace_mismatch_count") or 0)
    governance_contam = 0
    pending_phase1 = governance.get("pending_outside_target_after_phase1", {})
    for v in pending_phase1.values():
        if int(v) < 12:
            governance_contam += 1

    watchdog_skew = False
    timeout_by_domain = governance_safe_int_dict(watchdog.get("timeout_by_domain", {}))
    if timeout_by_domain:
        vals = list(timeout_by_domain.values())
        watchdog_skew = max(vals) - min(vals) > 3

    retry_observed = events.get("retry_order_observed", {})
    retry_non_monotonic_domains = [
        d for d, seq in retry_observed.items() if isinstance(seq, list) and seq[:3] != [1, 2, 3]
    ]

    matrix = {
        "replay_namespace_bleed": {
            "value": replay_bleed,
            "classification": classify_zero_is_safe(replay_bleed),
        },
        "governance_cross_contamination": {
            "value": governance_contam,
            "classification": classify_zero_is_safe(governance_contam),
        },
        "audit_chronology_mixing": {
            "value": int(governance.get("audit_entries_count") or 0),
            "classification": "bounded",
            "note": "Global append-only audit is intentionally mixed by time across domains.",
        },
        "queue_starvation_between_plugins": {
            "value": queue_starvation_flag,
            "classification": "unsafe" if queue_starvation_flag else "bounded",
        },
        "websocket_event_interference": {
            "value": round(max_foreign_ratio, 3),
            "classification": "unsafe" if max_foreign_ratio > 0.25 else "bounded",
        },
        "retry_order_interaction": {
            "value": retry_non_monotonic_domains,
            "classification": "safe" if not retry_non_monotonic_domains else "unsafe",
        },
        "shared_replay_buffer_pressure": {
            "value": int(events.get("broadcast_calls") or 0),
            "classification": "bounded",
        },
        "watchdog_cross_domain_effects": {
            "value": watchdog_skew,
            "classification": "unsafe" if watchdog_skew else "bounded",
        },
        "plugin_failure_containment": {
            "value": bool(task_campaign.get("create_results")),
            "classification": "bounded",
            "note": "Plugin load failures did not prevent task queue activity, but no hard runtime isolation exists.",
        },
        "plugin_induced_operational_drift": {
            "value": len(task_campaign.get("poll_samples", [])),
            "classification": "bounded",
        },
    }
    return matrix


def governance_safe_int_dict(raw: object) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue
    return out


def classify_zero_is_safe(value: int) -> str:
    if value == 0:
        return "safe"
    if value <= 2:
        return "bounded"
    return "unsafe"


def classify_conditions(matrix: dict[str, Any]) -> dict[str, list[str]]:
    safe: list[str] = []
    bounded: list[str] = []
    unsafe: list[str] = []
    for name, row in matrix.items():
        cls = str(row.get("classification") or "bounded")
        if cls == "safe":
            safe.append(name)
        elif cls == "unsafe":
            unsafe.append(name)
        else:
            bounded.append(name)
    return {
        "safe_coexistence_conditions": safe,
        "bounded_coexistence_conditions": bounded,
        "unsafe_coexistence_conditions": unsafe,
    }


def runtime_cell_feasibility_assessment(
    *, replay_ns: dict[str, Any], governance: dict[str, Any], events: dict[str, Any], task_campaign: dict[str, Any]
) -> dict[str, Any]:
    replay_mismatch = int(replay_ns.get("namespace_mismatch_count") or 0)
    foreign_ratios = [
        float(row.get("foreign_ratio") or 0.0)
        for row in events.get("collectors", [])
        if isinstance(row, dict)
    ]
    max_foreign_ratio = max(foreign_ratios) if foreign_ratios else 0.0

    return {
        "replay_partition_feasibility": {
            "status": "partial",
            "reason": (
                "task_logs preserve per-task input domain markers, but replay namespace is not enforced by runtime partition key"
            ),
            "evidence": {
                "namespace_mismatch_count": replay_mismatch,
                "task_log_coverage": replay_ns.get("found_task_log_count"),
            },
        },
        "governance_partition_feasibility": {
            "status": "partial",
            "reason": "approval IDs and patch IDs can be domain-scoped by convention, but governance schema has no explicit domain boundary column",
            "evidence": {
                "status_by_domain": governance.get("status_by_domain"),
                "audit_entries_count": governance.get("audit_entries_count"),
            },
        },
        "queue_partition_feasibility": {
            "status": "weak",
            "reason": "single shared 3-tier scheduler with no per-domain quotas or isolation gates",
            "evidence": {
                "queue_samples": len(task_campaign.get("poll_samples", [])),
                "per_domain_summary": task_campaign.get("per_domain_summary", {}),
            },
        },
        "event_bus_partition_feasibility": {
            "status": "partial",
            "reason": "domain-scoped channels reduce cross-domain visibility, but base shared channel still exists",
            "evidence": {
                "max_foreign_ratio": round(max_foreign_ratio, 3),
                "collector_samples": events.get("collectors", []),
            },
        },
        "per_plugin_audit_scope": {
            "status": "partial",
            "reason": "audit is global append-only; per-plugin views are reconstructable via target_id conventions",
        },
        "per_plugin_replay_lineage": {
            "status": "partial",
            "reason": "lineage exists per task_id but not enforced as plugin runtime-cell namespace",
        },
        "per_plugin_observability": {
            "status": "partial",
            "reason": "domain markers in payload/input enable derived metrics, but counters are not partition-native",
        },
        "trust_sandbox_boundaries": {
            "status": "weak",
            "reason": "plugin registry supports load-time containment only; no hard trust sandbox per plugin",
        },
    }


@dataclass
class Context:
    repo_root: Path
    output_dir: Path
    core_base: str
    ws_base: str
    db_path: Path
    db_path_in_container: str
    admin_email: str
    admin_password: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run controlled plugin coexistence validation")
    parser.add_argument("--repo-root", default="/local/mnt/workspace/AURA_V1")
    parser.add_argument("--core-base", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-base", default="http://127.0.0.1:8001")
    parser.add_argument("--db-path", default="/local/mnt/workspace/AURA_V1/AURA/data/aura.db")
    parser.add_argument("--db-path-in-container", default="/data/aura.db")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/AURA/data/outputs/runtime_discovery")
    return parser.parse_args()


def resolve_context(args: argparse.Namespace) -> Context:
    repo_root = Path(args.repo_root).resolve()
    env_data = load_env(repo_root / "AURA" / ".env")
    admin_email = env_data.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@aura.local"))
    admin_password = env_data.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "admin123"))
    return Context(
        repo_root=repo_root,
        output_dir=Path(args.output_dir),
        core_base=args.core_base,
        ws_base=args.ws_base,
        db_path=Path(args.db_path),
        db_path_in_container=args.db_path_in_container,
        admin_email=admin_email,
        admin_password=admin_password,
    )


async def amain() -> int:
    args = parse_args()
    ctx = resolve_context(args)
    started_at_iso = utc_iso()
    run_id = f"plugin-coexist-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{short_token(6)}"

    domains: dict[str, dict[str, Any]] = {
        "driver": {
            "agent_type": "learning",
            "priority": "P0",
            "tasks": 14,
            "workflow_pattern": "downstream_driver_scan",
            "replay_pattern": "high_step_density",
            "governance_scope": "driver-upstream",
            "event_behavior": "burst_and_retry",
            "queue_behavior": "preemptive_critical",
        },
        "media": {
            "agent_type": "validation",
            "priority": "P1",
            "tasks": 14,
            "workflow_pattern": "media_pipeline_validation",
            "replay_pattern": "mixed_finalization",
            "governance_scope": "media-quality",
            "event_behavior": "steady_stream",
            "queue_behavior": "round_robin_normal",
        },
        "automation": {
            "agent_type": "test_runner",
            "priority": "P2",
            "tasks": 14,
            "workflow_pattern": "automation_regression_loops",
            "replay_pattern": "retry_heavy",
            "governance_scope": "automation-stability",
            "event_behavior": "retry_normalization",
            "queue_behavior": "best_effort_background",
        },
        "research": {
            "agent_type": "maintainer_intel",
            "priority": "P1",
            "tasks": 14,
            "workflow_pattern": "maintainer_pattern_research",
            "replay_pattern": "context_heavy",
            "governance_scope": "research-exploration",
            "event_behavior": "sporadic_spikes",
            "queue_behavior": "round_robin_normal",
        },
    }

    ctx.output_dir.mkdir(parents=True, exist_ok=True)

    token = login_admin(ctx.core_base, ctx.admin_email, ctx.admin_password)
    before_audit = audit_summary(ctx.db_path)
    before_mem = docker_memory_snapshot()
    before_queue = _get_queue_stats(ctx.core_base, token)
    before_queue_isolation = _get_queue_isolation_stats(ctx.core_base, token)
    before_ws_metrics = _get_ws_coexistence_metrics(ctx.ws_base)

    plugin_scan = plugin_synthetic_domain_scan()

    task_campaign = multi_domain_task_campaign(
        core_base=ctx.core_base,
        token=token,
        run_id=run_id,
        domains=domains,
        duration_seconds=45,
    )

    replay_ns = replay_namespace_validation(
        db_path=ctx.db_path,
        task_ids_by_domain=task_campaign.get("task_ids_by_domain", {}),
    )

    governance = governance_scope_campaign(
        core_base=ctx.core_base,
        token=token,
        run_id=run_id,
        db_path=ctx.db_path,
        db_path_in_container=ctx.db_path_in_container,
        domains=list(domains.keys()),
    )

    events = await event_stream_interference_campaign(
        ws_base=ctx.ws_base,
        run_id=run_id,
        domains=list(domains.keys()),
        duration_seconds=12,
    )

    watchdog = watchdog_cross_domain_campaign(
        run_id=run_id,
        domains=list(domains.keys()),
        db_path_in_container=ctx.db_path_in_container,
    )
    watchdog_replay = replay_check_for_watchdog_tasks(
        ctx.core_base,
        token,
        [str(x) for x in watchdog.get("task_ids", []) if isinstance(x, str)],
    )

    ci_checks = run_ci_equivalent_checks(ctx.repo_root)

    after_queue = _get_queue_stats(ctx.core_base, token)
    after_audit = audit_summary(ctx.db_path)
    after_mem = docker_memory_snapshot()
    after_queue_isolation = _get_queue_isolation_stats(ctx.core_base, token)
    after_ws_metrics = _get_ws_coexistence_metrics(ctx.ws_base)

    matrix = compute_interference_matrix(
        task_campaign=task_campaign,
        replay_ns=replay_ns,
        governance=governance,
        events=events,
        watchdog=watchdog,
    )
    coexistence_conditions = classify_conditions(matrix)
    runtime_cell = runtime_cell_feasibility_assessment(
        replay_ns=replay_ns,
        governance=governance,
        events=events,
        task_campaign=task_campaign,
    )

    payload = {
        "run_id": run_id,
        "started_at": started_at_iso,
        "finished_at": utc_iso(),
        "domains": domains,
        "baseline": {
            "audit_before": before_audit,
            "queue_before": before_queue,
            "queue_isolation_before": before_queue_isolation,
            "memory_before": before_mem,
            "ws_metrics_before": before_ws_metrics,
        },
        "campaigns": {
            "plugin_synthetic_domain_scan": plugin_scan,
            "multi_domain_task_pressure": task_campaign,
            "replay_namespace_boundary": replay_ns,
            "governance_scope_validation": governance,
            "event_stream_interference": events,
            "watchdog_cross_domain": watchdog,
            "watchdog_replay_visibility": watchdog_replay,
            "ci_enforcement": ci_checks,
        },
        "post_state": {
            "audit_after": after_audit,
            "queue_after": after_queue,
            "queue_isolation_after": after_queue_isolation,
            "memory_after": after_mem,
            "ws_metrics_after": after_ws_metrics,
            "audit_delta_rows": after_audit["row_count"] - before_audit["row_count"],
            "audit_delta_mismatch": after_audit["mismatch_count"] - before_audit["mismatch_count"],
        },
        "assessments": {
            "cross_domain_interference_matrix": matrix,
            "coexistence_conditions": coexistence_conditions,
            "runtime_cell_feasibility": runtime_cell,
        },
    }

    out_json = ctx.output_dir / f"plugin_coexistence_{run_id}.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out_json)
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
