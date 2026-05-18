#!/usr/bin/env python3
"""Controlled endurance and operational resilience validation.

Runs sustained pressure campaigns against the current AURA runtime without
changing architecture shape. Produces evidence artifacts for:
- soak stability/drift
- replay/governance integrity under load
- websocket churn/reconnect pressure
- queue pressure
- WAL contention characterization
- plugin boundary pressure signals
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sqlite3
import statistics
import string
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import websockets


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


def run_p1_round(
    *,
    repo_root: Path,
    core_base: str,
    ws_base: str,
    db_path_in_container: str,
    output_dir_in_container: str,
    run_id: str,
) -> Path:
    script_host = repo_root / "AURA" / "scripts" / "p1_adversarial_rerun.py"
    copy_cmd = ["docker", "cp", str(script_host), "aura-core:/tmp/p1_adversarial_rerun.py"]
    subprocess.run(copy_cmd, check=True)

    exec_cmd = [
        "docker",
        "exec",
        "aura-core",
        "sh",
        "-lc",
        (
            "PYTHONPATH=/workspace/aura-sdk/src:/app/src "
            "python /tmp/p1_adversarial_rerun.py "
            f"--core-base {core_base} "
            f"--ws-base {ws_base} "
            f"--db-path {db_path_in_container} "
            f"--output-dir {output_dir_in_container} "
            f"--run-id {run_id}"
        ),
    ]
    proc = subprocess.run(exec_cmd, capture_output=True, text=True, check=True)

    artifact_in_container = ""
    for line in proc.stdout.splitlines():
        raw = line.strip()
        if raw.endswith(".json") and "/runtime_discovery_" in raw:
            artifact_in_container = raw
    if not artifact_in_container:
        raise RuntimeError(f"failed to parse p1 artifact path for run_id={run_id}")

    prefix = "/data/outputs/runtime_discovery/"
    if not artifact_in_container.startswith(prefix):
        raise RuntimeError(f"unexpected artifact path: {artifact_in_container}")
    rel_name = artifact_in_container[len(prefix):]
    artifact_host = repo_root / "AURA" / "data" / "outputs" / "runtime_discovery" / rel_name
    if not artifact_host.exists():
        raise RuntimeError(f"artifact not found on host: {artifact_host}")
    return artifact_host


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_area(payload: dict[str, Any], name: str) -> dict[str, Any]:
    for item in payload.get("test_results", []):
        if item.get("test_area") == name:
            return item
    raise KeyError(name)


def summarize_severity(payload: dict[str, Any]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for item in payload.get("test_results", []):
        key = str(item.get("severity_classification", "info"))
        if key not in counts:
            key = "info"
        counts[key] += 1
    return counts


async def websocket_reconnect_storm(
    *,
    ws_base: str,
    duration_seconds: int,
    fast_clients: int,
    slow_clients: int,
    reconnect_loops: int,
) -> dict[str, Any]:
    ws_url = ws_base.replace("http://", "ws://") + "/ws"
    marker = f"soak-ws-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{short_token(5)}"
    event_type = "runtime.soak.ws"

    stats: dict[str, dict[str, int]] = {}
    for i in range(fast_clients):
        stats[f"fast-{i}"] = {"reconnects": 0, "received": 0, "errors": 0}
    for i in range(slow_clients):
        stats[f"slow-{i}"] = {"reconnects": 0, "received": 0, "errors": 0}
    stats["monitor"] = {"reconnects": 0, "received": 0, "errors": 0}

    ordering_anomalies = {"ingest_non_monotonic": 0}

    async def _client(name: str, slow: bool, monitor: bool = False) -> None:
        per_loop = max(1.0, duration_seconds / max(1, reconnect_loops))
        for _ in range(reconnect_loops):
            loop_deadline = time.time() + per_loop
            try:
                stats[name]["reconnects"] += 1
                async with websockets.connect(ws_url, open_timeout=5, close_timeout=2) as ws:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=3.0)
                    except Exception:
                        pass
                    await ws.send(json.dumps({"action": "subscribe", "channels": ["system"]}))

                    last_ingest: int | None = None
                    while time.time() < loop_deadline:
                        timeout = max(0.05, loop_deadline - time.time())
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            stats[name]["errors"] += 1
                            break
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(data, dict):
                            continue
                        payload = data.get("payload")
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("marker") != marker:
                            continue
                        stats[name]["received"] += 1
                        if monitor:
                            ordering = data.get("_ordering")
                            if isinstance(ordering, dict):
                                ingest = ordering.get("ingest_sequence")
                                if isinstance(ingest, int):
                                    if last_ingest is not None and ingest <= last_ingest:
                                        ordering_anomalies["ingest_non_monotonic"] += 1
                                    last_ingest = ingest
                        if slow:
                            await asyncio.sleep(0.04)
            except Exception:
                stats[name]["errors"] += 1

    async def _broadcast_loop() -> dict[str, int]:
        sent = 0
        duplicate_injected = 0
        start = time.time()
        interval = 0.03
        while time.time() - start < duration_seconds:
            seq = sent
            event = {
                "event_id": f"{marker}-{seq}",
                "event_type": event_type,
                "timestamp": utc_iso(),
                "payload": {"marker": marker, "seq": seq},
            }
            try:
                await asyncio.to_thread(
                    requests.post,
                    f"{ws_base}/broadcast",
                    json={"channel": "system", "event": event},
                    timeout=10,
                )
                sent += 1
            except Exception:
                pass

            if seq % 50 == 0:
                duplicate_injected += 1
                try:
                    await asyncio.to_thread(
                        requests.post,
                        f"{ws_base}/broadcast",
                        json={"channel": "system", "event": event},
                        timeout=10,
                    )
                except Exception:
                    pass
            await asyncio.sleep(interval)
        return {"sent": sent, "duplicate_injected": duplicate_injected}

    async def _collect_sse_replay(seconds: float) -> int:
        count = 0
        started = time.time()
        try:
            with requests.get(
                f"{ws_base}/events?channels=system",
                stream=True,
                timeout=10,
            ) as resp:
                for raw in resp.iter_lines(decode_unicode=True):
                    if time.time() - started > seconds:
                        break
                    if not raw or not raw.startswith("data: "):
                        continue
                    try:
                        data = json.loads(raw[6:])
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    payload = data.get("payload")
                    if isinstance(payload, dict) and payload.get("marker") == marker:
                        count += 1
        except Exception:
            return count
        return count

    client_tasks: list[asyncio.Task[None]] = []
    for i in range(fast_clients):
        client_tasks.append(asyncio.create_task(_client(f"fast-{i}", slow=False)))
    for i in range(slow_clients):
        client_tasks.append(asyncio.create_task(_client(f"slow-{i}", slow=True)))
    client_tasks.append(asyncio.create_task(_client("monitor", slow=False, monitor=True)))
    broadcast_task = asyncio.create_task(_broadcast_loop())

    await asyncio.gather(*client_tasks)
    broadcast_result = await broadcast_task
    replay_count = await _collect_sse_replay(seconds=3.0)

    total_received = sum(v["received"] for v in stats.values())
    total_errors = sum(v["errors"] for v in stats.values())
    total_reconnects = sum(v["reconnects"] for v in stats.values())
    dropped_estimate = max(0, broadcast_result["sent"] - replay_count)
    return {
        "marker": marker,
        "duration_seconds": duration_seconds,
        "broadcast": broadcast_result,
        "client_stats": stats,
        "total_received": total_received,
        "total_errors": total_errors,
        "total_reconnects": total_reconnects,
        "replayed_count": replay_count,
        "dropped_estimate": dropped_estimate,
        "ordering_anomalies": ordering_anomalies,
    }


def _ensure_governance_fixture_container(
    *, db_path_in_container: str, run_id: str, count: int
) -> list[str]:
    script = f"""
import json
import sqlite3
import time

db_path = {json.dumps(db_path_in_container)}
run_id = {json.dumps(run_id)}
count = {count}
con = sqlite3.connect(db_path)
now_ts = int(time.time())
row = con.execute("SELECT id FROM subsystems ORDER BY created_at LIMIT 1").fetchone()
subsystem_id = row[0] if row else None
patch_id = f"soak-patch-{{run_id}}"
con.execute(
    '''
    INSERT OR REPLACE INTO patches (id, subsystem_id, version, status, title, description, generated_by, created_at, updated_at)
    VALUES (?, ?, 1, 'reviewing', ?, ?, 'soak', ?, ?)
    ''',
    (patch_id, subsystem_id, f"Soak patch {{run_id}}", "governance latency fixture", now_ts, now_ts),
)
approval_ids = []
dimensions = ["lifecycle", "subsystem", "quality"]
for i in range(count):
    aid = f"soak-appr-{{run_id}}-{{i}}"
    approval_ids.append(aid)
    con.execute(
        '''
        INSERT OR REPLACE INTO approvals (id, patch_id, dimension, stage, status, created_at, updated_at)
        VALUES (?, ?, ?, 'review', 'pending', ?, ?)
        ''',
        (aid, patch_id, dimensions[i % len(dimensions)], now_ts, now_ts),
    )
con.commit()
con.close()
print(json.dumps({{"approval_ids": approval_ids}}))
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
    for line in reversed(proc.stdout.splitlines()):
        raw = line.strip()
        if not raw or not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ids = payload.get("approval_ids")
        if isinstance(ids, list) and ids:
            return [str(x) for x in ids]
    raise RuntimeError(f"failed to parse container governance fixture output: {proc.stdout}")


def ensure_governance_fixture(
    db_path: Path, run_id: str, count: int = 40, db_path_in_container: str = "/data/aura.db"
) -> list[str]:
    try:
        con = sqlite3.connect(str(db_path))
        now_ts = int(time.time())
        row = con.execute("SELECT id FROM subsystems ORDER BY created_at LIMIT 1").fetchone()
        subsystem_id = row[0] if row else None
        patch_id = f"soak-patch-{run_id}"
        con.execute(
            """
            INSERT OR REPLACE INTO patches (id, subsystem_id, version, status, title, description, generated_by, created_at, updated_at)
            VALUES (?, ?, 1, 'reviewing', ?, ?, 'soak', ?, ?)
            """,
            (patch_id, subsystem_id, f"Soak patch {run_id}", "governance latency fixture", now_ts, now_ts),
        )
        approval_ids: list[str] = []
        dimensions = ["lifecycle", "subsystem", "quality"]
        for i in range(count):
            aid = f"soak-appr-{run_id}-{i}"
            approval_ids.append(aid)
            con.execute(
                """
                INSERT OR REPLACE INTO approvals (id, patch_id, dimension, stage, status, created_at, updated_at)
                VALUES (?, ?, ?, 'review', 'pending', ?, ?)
                """,
                (aid, patch_id, dimensions[i % len(dimensions)], now_ts, now_ts),
            )
        con.commit()
        con.close()
        return approval_ids
    except sqlite3.OperationalError as exc:
        if "unknown function: unixepoch" not in str(exc).lower():
            raise
        return _ensure_governance_fixture_container(
            db_path_in_container=db_path_in_container,
            run_id=run_id,
            count=count,
        )


def governance_latency_campaign(
    *,
    core_base: str,
    token: str,
    db_path: Path,
    db_path_in_container: str,
    duration_seconds: int,
) -> dict[str, Any]:
    run_id = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{short_token(5)}"
    approval_ids = ensure_governance_fixture(
        db_path, run_id=run_id, count=40, db_path_in_container=db_path_in_container
    )
    headers = auth_headers(token)
    before = audit_summary(db_path)
    started = time.time()
    latencies_ms: list[float] = []
    status_counter: Counter[int] = Counter()
    action_counter: Counter[str] = Counter()

    actions = ["grant", "reject", "comment", "escalate"]
    rand = random.Random(42)

    def _one_call(aid: str, action: str, comment: str) -> tuple[int, float]:
        t0 = time.perf_counter()
        r = requests.post(
            f"{core_base}/api/v1/governance/approvals/{aid}",
            headers=headers,
            json={"action": action, "comment": comment},
            timeout=15,
        )
        dt = (time.perf_counter() - t0) * 1000.0
        return r.status_code, dt

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = []
        i = 0
        while time.time() - started < duration_seconds:
            aid = approval_ids[i % len(approval_ids)]
            action = actions[i % len(actions)]
            action_counter[action] += 1
            futures.append(pool.submit(_one_call, aid, action, f"soak-{i}-{action}"))
            i += 1
            if len(futures) >= 200:
                break
        for f in as_completed(futures):
            try:
                status, latency = f.result()
            except Exception:
                status_counter[599] += 1
                latencies_ms.append(15000.0)
                continue
            status_counter[status] += 1
            latencies_ms.append(latency)

    after = audit_summary(db_path)
    lat_sorted = sorted(latencies_ms) if latencies_ms else [0.0]
    p50 = lat_sorted[int(0.50 * (len(lat_sorted) - 1))]
    p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))]
    p99 = lat_sorted[int(0.99 * (len(lat_sorted) - 1))]
    return {
        "run_id": run_id,
        "duration_seconds": duration_seconds,
        "requests_total": len(latencies_ms),
        "status_counts": dict(status_counter),
        "action_counts": dict(action_counter),
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "p99": round(p99, 3),
            "max": round(max(latencies_ms), 3) if latencies_ms else 0.0,
        },
        "audit_before": before,
        "audit_after": after,
        "audit_delta_rows": after["row_count"] - before["row_count"],
        "audit_delta_mismatch": after["mismatch_count"] - before["mismatch_count"],
    }


def plugin_pressure_campaign() -> dict[str, Any]:
    script = r"""
import asyncio
import json
import tempfile
import time
from pathlib import Path

from aura_sdk.plugins.interface import SubsystemPlugin, PluginMetadata, PluginCapability
from aura_sdk.plugins.registry import PluginRegistry

def _write_good_plugin(root: Path, pkg: str, name: str) -> None:
    p = root / pkg
    p.mkdir(parents=True, exist_ok=True)
    (p / "__init__.py").write_text(
        "\n".join([
            "from pathlib import Path",
            "from typing import Any",
            "from aura_sdk.plugins.interface import SubsystemPlugin, PluginMetadata, PluginCapability",
            "class Plugin(SubsystemPlugin):",
            "    def _init_metadata(self):",
            f"        return PluginMetadata(name='{name}', display_name='{name}', capabilities=[PluginCapability.RULE_DISCOVERY])",
            "    async def load_rules(self, rules_path: Path): return []",
            "    async def validate_patch(self, patch_path: Path, context: dict[str, Any]): return {'valid': True, 'findings': [], 'confidence': 0.5}",
            "    async def suggest_fix(self, issue: dict[str, Any], context: dict[str, Any]): return {'suggestion': 'noop', 'confidence': 0.5}",
            "",
        ]),
        encoding="utf-8",
    )

def _write_bad_plugin(root: Path, pkg: str) -> None:
    p = root / pkg
    p.mkdir(parents=True, exist_ok=True)
    (p / "__init__.py").write_text("raise RuntimeError('plugin failure injection')\n", encoding="utf-8")

async def main() -> None:
    rounds = 15
    good = 12
    bad = 8
    load_counts = []
    durations = []
    overwrite_detected = False

    with tempfile.TemporaryDirectory(prefix='aura-plugin-pressure-') as td:
        root = Path(td)
        for i in range(good):
            _write_good_plugin(root, f'good_{i}', f'good-plugin-{i}')
        for i in range(bad):
            _write_bad_plugin(root, f'bad_{i}')
        # Intentional metadata collision to expose overwrite behavior.
        _write_good_plugin(root, 'dup_a', 'dup-shared')
        _write_good_plugin(root, 'dup_b', 'dup-shared')

        for _ in range(rounds):
            reg = PluginRegistry()
            t0 = time.perf_counter()
            loaded = await reg.scan_directory(root)
            dt = (time.perf_counter() - t0) * 1000.0
            load_counts.append(int(loaded))
            durations.append(dt)
            names = reg.list_plugins()
            if len(names) < loaded:
                overwrite_detected = True

    out = {
        "rounds": rounds,
        "good_packages": good + 2,
        "bad_packages": bad,
        "load_count_min": min(load_counts) if load_counts else 0,
        "load_count_max": max(load_counts) if load_counts else 0,
        "duration_ms_p95": sorted(durations)[int(0.95 * (len(durations) - 1))] if durations else 0.0,
        "duration_ms_max": max(durations) if durations else 0.0,
        "overwrite_detected": overwrite_detected,
        "failure_containment_ok": min(load_counts) >= good,
    }
    print(json.dumps(out))

asyncio.run(main())
"""
    cmd = [
        "docker",
        "exec",
        "aura-core",
        "sh",
        "-lc",
        f"PYTHONPATH=/workspace/aura-sdk/src:/app/src python - <<'PY'\n{script}\nPY",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    line = ""
    for raw in proc.stdout.splitlines():
        raw = raw.strip()
        if raw.startswith("{") and raw.endswith("}"):
            line = raw
    if not line:
        raise RuntimeError(f"plugin pressure output not found: {proc.stdout}")
    return json.loads(line)


def replay_burst_campaign(
    *,
    core_base: str,
    token: str,
    task_ids: list[str],
    duration_seconds: int,
) -> dict[str, Any]:
    headers = auth_headers(token)
    started = time.time()
    status_counter: Counter[int] = Counter()
    latency_ms: list[float] = []
    first_success_lag: dict[str, float] = {}

    if not task_ids:
        return {
            "duration_seconds": duration_seconds,
            "requests_total": 0,
            "status_counts": {},
            "latency_ms": {"p50": 0.0, "p95": 0.0, "max": 0.0},
            "first_success_lag_stats": {"count": 0},
        }

    idx = 0
    while time.time() - started < duration_seconds:
        task_id = task_ids[idx % len(task_ids)]
        idx += 1
        t0 = time.perf_counter()
        try:
            r = requests.get(
                f"{core_base}/api/v1/tasks/{task_id}/replay",
                headers=headers,
                timeout=10,
            )
            dt = (time.perf_counter() - t0) * 1000.0
            status_counter[r.status_code] += 1
            latency_ms.append(dt)
            if r.status_code == 200 and task_id not in first_success_lag:
                first_success_lag[task_id] = time.time() - started
        except Exception:
            status_counter[599] += 1
            latency_ms.append(10000.0)
        time.sleep(0.03)

    lat_sorted = sorted(latency_ms) if latency_ms else [0.0]
    p50 = lat_sorted[int(0.50 * (len(lat_sorted) - 1))]
    p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))]
    first_lags = sorted(first_success_lag.values())
    lag_stats = {"count": len(first_lags)}
    if first_lags:
        lag_stats["p50"] = round(first_lags[int(0.50 * (len(first_lags) - 1))], 3)
        lag_stats["p95"] = round(first_lags[int(0.95 * (len(first_lags) - 1))], 3)
        lag_stats["max"] = round(max(first_lags), 3)
    return {
        "duration_seconds": duration_seconds,
        "requests_total": len(latency_ms),
        "status_counts": dict(status_counter),
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "max": round(max(latency_ms), 3) if latency_ms else 0.0,
        },
        "first_success_lag_stats": lag_stats,
    }


def wal_characterization_campaign(duration_loops: int = 8) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    def _attempt(path: Path, timeout: float, retries: int) -> dict[str, Any]:
        attempts = 0
        for i in range(retries + 1):
            attempts += 1
            try:
                con = sqlite3.connect(str(path), timeout=timeout)
                con.execute("INSERT INTO t(v) VALUES (?)", (f"v-{time.time_ns()}",))
                con.commit()
                con.close()
                return {"ok": True, "attempts": attempts}
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or i == retries:
                    return {"ok": False, "attempts": attempts, "error": str(exc)}
                time.sleep(0.01 * (i + 1))
            except Exception as exc:
                return {"ok": False, "attempts": attempts, "error": str(exc)}
        return {"ok": False, "attempts": attempts, "error": "unknown"}

    with sqlite3.connect(":memory:"):
        pass

    tmp = Path("/tmp") / f"aura-soak-wal-{short_token(6)}.db"
    con = sqlite3.connect(str(tmp), timeout=0.1)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS t(id INTEGER PRIMARY KEY, v TEXT)")
    con.commit()
    con.close()

    for _ in range(duration_loops):
        lock = sqlite3.connect(str(tmp), timeout=0.0)
        lock.execute("BEGIN EXCLUSIVE")
        lock.execute("INSERT INTO t(v) VALUES ('lock-holder')")
        no_retry = [_attempt(tmp, timeout=0.0, retries=0) for _ in range(20)]
        with_retry = [_attempt(tmp, timeout=0.0, retries=7) for _ in range(20)]
        busy_timeout = [_attempt(tmp, timeout=0.2, retries=0) for _ in range(10)]

        ck_rows: list[list[int]] = []
        ck = sqlite3.connect(str(tmp), timeout=0.2)
        for _ in range(10):
            row = ck.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            if row:
                ck_rows.append([int(row[0]), int(row[1]), int(row[2])])
        ck.close()
        lock.rollback()
        lock.close()
        results.append(
            {
                "no_retry_failures": sum(1 for x in no_retry if not x.get("ok")),
                "with_retry_failures": sum(1 for x in with_retry if not x.get("ok")),
                "busy_timeout_failures": sum(1 for x in busy_timeout if not x.get("ok")),
                "checkpoint_samples": ck_rows,
            }
        )

    if tmp.exists():
        tmp.unlink(missing_ok=True)
        (tmp.with_suffix(".db-wal")).unlink(missing_ok=True)
        (tmp.with_suffix(".db-shm")).unlink(missing_ok=True)

    return {
        "loops": duration_loops,
        "results": results,
        "no_retry_failures_total": sum(r["no_retry_failures"] for r in results),
        "with_retry_failures_total": sum(r["with_retry_failures"] for r in results),
        "busy_timeout_failures_total": sum(r["busy_timeout_failures"] for r in results),
    }


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


def aggregate_round_metrics(round_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    per_round: list[dict[str, Any]] = []
    for p in round_payloads:
        run_id = str(p.get("run_id") or "")
        sev = summarize_severity(p)
        concurrent = find_area(p, "concurrent_task_execution")
        ordering = find_area(p, "event_ordering_pressure")
        wal = find_area(p, "sqlite_wal_stress")
        ws = find_area(p, "websocket_sse_instability")
        replay = find_area(p, "replay_stress_validation")
        gov = find_area(p, "governance_pressure_testing")
        watchdog = find_area(p, "watchdog_pressure_testing")

        per_round.append(
            {
                "run_id": run_id,
                "severity": sev,
                "replay_coverage_ratio": concurrent.get("replay_integrity_result", {}).get("coverage_ratio"),
                "final_replay_non_200": concurrent.get("replay_integrity_result", {}).get("final_replay_non_200"),
                "max_overlapping_running": concurrent.get("observed_behavior", {}).get("max_overlapping_running"),
                "event_retry_order": ordering.get("observed_behavior", {}).get("retry_order_delivery"),
                "event_drop_estimate": ordering.get("observed_behavior", {}).get("estimated_dropped_in_replay_buffer"),
                "ws_error_count": ws.get("observed_behavior", {}).get("ws_error_count"),
                "ws_recipients_min": ws.get("observed_behavior", {}).get("broadcast_recipients_min"),
                "ws_recipients_max": ws.get("observed_behavior", {}).get("broadcast_recipients_max"),
                "wal_with_retry_failures": wal.get("observed_behavior", {}).get("with_retry_failures"),
                "governance_conflict_statuses": gov.get("observed_behavior", {}).get("conflict_statuses"),
                "governance_contention_success": gov.get("observed_behavior", {}).get("contention_success"),
                "governance_contention_fail": gov.get("observed_behavior", {}).get("contention_fail"),
                "watchdog_missing_replay_count": watchdog.get("replay_integrity_result", {}).get("missing_replay_count", 0),
                "stable_replay_hash_count": replay.get("observed_behavior", {}).get("stable_replay_hash_count"),
            }
        )

    drift: dict[str, Any] = {
        "rounds": per_round,
        "severity_trajectory": [r["severity"] for r in per_round],
    }
    if per_round:
        drift["event_drop_estimate_range"] = {
            "min": min(int(r["event_drop_estimate"] or 0) for r in per_round),
            "max": max(int(r["event_drop_estimate"] or 0) for r in per_round),
        }
        drift["replay_coverage_range"] = {
            "min": min(float(r["replay_coverage_ratio"] or 0.0) for r in per_round),
            "max": max(float(r["replay_coverage_ratio"] or 0.0) for r in per_round),
        }
    return drift


@dataclass
class Context:
    repo_root: Path
    core_base: str
    ws_base: str
    db_path_host: Path
    db_path_in_container: str
    output_dir_host: Path
    output_dir_in_container: str
    rounds: int
    round_interval_seconds: int
    ws_storm_seconds: int
    governance_seconds: int
    replay_burst_seconds: int
    wal_loops: int
    admin_email: str
    admin_password: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run endurance soak validation campaigns")
    parser.add_argument("--repo-root", default="/local/mnt/workspace/AURA_V1")
    parser.add_argument("--core-base", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-base", default="http://127.0.0.1:8001")
    parser.add_argument("--db-path-host", default="/local/mnt/workspace/AURA_V1/AURA/data/aura.db")
    parser.add_argument("--db-path-in-container", default="/data/aura.db")
    parser.add_argument("--output-dir-host", default="/local/mnt/workspace/AURA_V1/AURA/data/outputs/runtime_discovery")
    parser.add_argument("--output-dir-in-container", default="/data/outputs/runtime_discovery")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--round-interval-seconds", type=int, default=15)
    parser.add_argument("--ws-storm-seconds", type=int, default=150)
    parser.add_argument("--governance-seconds", type=int, default=120)
    parser.add_argument("--replay-burst-seconds", type=int, default=90)
    parser.add_argument("--wal-loops", type=int, default=10)
    return parser.parse_args()


def resolve_context(args: argparse.Namespace) -> Context:
    repo_root = Path(args.repo_root).resolve()
    env_data = load_env(repo_root / "AURA" / ".env")
    admin_email = env_data.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "nandam@qti.qualcomm.com"))
    admin_password = env_data.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "Gummal@123"))
    return Context(
        repo_root=repo_root,
        core_base=args.core_base,
        ws_base=args.ws_base,
        db_path_host=Path(args.db_path_host),
        db_path_in_container=args.db_path_in_container,
        output_dir_host=Path(args.output_dir_host),
        output_dir_in_container=args.output_dir_in_container,
        rounds=args.rounds,
        round_interval_seconds=args.round_interval_seconds,
        ws_storm_seconds=args.ws_storm_seconds,
        governance_seconds=args.governance_seconds,
        replay_burst_seconds=args.replay_burst_seconds,
        wal_loops=args.wal_loops,
        admin_email=admin_email,
        admin_password=admin_password,
    )


async def amain() -> int:
    args = parse_args()
    ctx = resolve_context(args)
    started_at_iso = utc_iso()
    run_id = f"endurance-soak-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{short_token(6)}"
    ctx.output_dir_host.mkdir(parents=True, exist_ok=True)

    token = login_admin(ctx.core_base, ctx.admin_email, ctx.admin_password)
    before_audit = audit_summary(ctx.db_path_host)
    before_mem = docker_memory_snapshot()

    round_artifacts: list[str] = []
    round_payloads: list[dict[str, Any]] = []
    round_memory: list[dict[str, Any]] = []
    replay_task_ids: list[str] = []

    for i in range(ctx.rounds):
        round_id = f"{run_id}-r{i+1}"
        artifact = run_p1_round(
            repo_root=ctx.repo_root,
            core_base=ctx.core_base,
            ws_base="http://ws-server:8000",
            db_path_in_container=ctx.db_path_in_container,
            output_dir_in_container=ctx.output_dir_in_container,
            run_id=round_id,
        )
        payload = load_json(artifact)
        round_artifacts.append(str(artifact))
        round_payloads.append(payload)
        round_memory.append({"run_id": round_id, "memory": docker_memory_snapshot()})
        try:
            concurrent = find_area(payload, "concurrent_task_execution")
            sample = (
                concurrent.get("runtime_evidence", [{}])[-1].get("created_task_ids_sample", [])
                if concurrent.get("runtime_evidence")
                else []
            )
            for task_id in sample:
                if isinstance(task_id, str):
                    replay_task_ids.append(task_id)
        except Exception:
            pass
        if i < ctx.rounds - 1:
            time.sleep(ctx.round_interval_seconds)

    ws_storm = await websocket_reconnect_storm(
        ws_base=ctx.ws_base,
        duration_seconds=ctx.ws_storm_seconds,
        fast_clients=12,
        slow_clients=6,
        reconnect_loops=4,
    )
    governance_latency = governance_latency_campaign(
        core_base=ctx.core_base,
        token=token,
        db_path=ctx.db_path_host,
        db_path_in_container=ctx.db_path_in_container,
        duration_seconds=ctx.governance_seconds,
    )
    plugin_pressure = plugin_pressure_campaign()
    replay_burst = replay_burst_campaign(
        core_base=ctx.core_base,
        token=token,
        task_ids=sorted(set(replay_task_ids))[:80],
        duration_seconds=ctx.replay_burst_seconds,
    )
    wal_pressure = wal_characterization_campaign(duration_loops=ctx.wal_loops)
    ci_checks = run_ci_equivalent_checks(ctx.repo_root)

    after_audit = audit_summary(ctx.db_path_host)
    after_mem = docker_memory_snapshot()

    drift = aggregate_round_metrics(round_payloads)

    observability = {
        "replay_lag": replay_burst.get("first_success_lag_stats", {}),
        "queue_depth_proxy": [
            {
                "run_id": row["run_id"],
                "max_overlapping_running": row.get("max_overlapping_running"),
            }
            for row in drift.get("rounds", [])
        ],
        "retry_drift": [
            {
                "run_id": row["run_id"],
                "retry_order": row.get("event_retry_order"),
                "is_monotonic": row.get("event_retry_order") == [1, 2, 3],
            }
            for row in drift.get("rounds", [])
        ],
        "websocket_reconnect_pressure": {
            "total_reconnects": ws_storm.get("total_reconnects"),
            "total_errors": ws_storm.get("total_errors"),
            "dropped_estimate": ws_storm.get("dropped_estimate"),
            "ordering_anomalies": ws_storm.get("ordering_anomalies", {}),
        },
        "wal_retry_pressure": {
            "with_retry_failures_total": wal_pressure.get("with_retry_failures_total"),
            "busy_timeout_failures_total": wal_pressure.get("busy_timeout_failures_total"),
        },
        "governance_latency": governance_latency.get("latency_ms", {}),
        "event_ordering_anomalies": drift.get("event_drop_estimate_range", {}),
        "replay_completeness": drift.get("replay_coverage_range", {}),
        "plugin_execution_metrics": plugin_pressure,
    }

    payload = {
        "run_id": run_id,
        "started_at": started_at_iso,
        "platform": {
            "core_base": ctx.core_base,
            "ws_base": ctx.ws_base,
            "db_path_host": str(ctx.db_path_host),
            "rounds": ctx.rounds,
        },
        "artifacts": {
            "round_artifacts": round_artifacts,
        },
        "campaigns": {
            "round_soak": drift,
            "ws_reconnect_storm": ws_storm,
            "governance_latency": governance_latency,
            "plugin_pressure": plugin_pressure,
            "replay_burst": replay_burst,
            "wal_pressure": wal_pressure,
        },
        "observability": observability,
        "integrity": {
            "audit_before": before_audit,
            "audit_after": after_audit,
            "audit_delta_rows": after_audit["row_count"] - before_audit["row_count"],
            "audit_delta_mismatch": after_audit["mismatch_count"] - before_audit["mismatch_count"],
            "memory_before": before_mem,
            "memory_after": after_mem,
            "memory_samples_per_round": round_memory,
            "ci_checks": ci_checks,
        },
        "finished_at": utc_iso(),
    }

    out_json = ctx.output_dir_host / f"endurance_soak_{run_id}.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out_json)
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
