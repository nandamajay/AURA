#!/usr/bin/env python3
"""Deterministic demo workload runner for AURA.

Creates a seeded task set, polls outcomes, and writes evidence artifact.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Config:
    api_base: str
    admin_email: str
    admin_password: str
    seed: int
    timeout_seconds: int
    poll_interval_seconds: float
    output_dir: Path


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deterministic_workload(seed: int) -> list[dict[str, Any]]:
    random.seed(seed)
    domains = ["driver", "media", "automation", "research"]
    agent_types = ["learning", "validation", "refactor", "simulation"]
    priorities = ["P1", "P2", "P1", "P2"]

    tasks: list[dict[str, Any]] = []
    for idx in range(8):
        domain = domains[idx % len(domains)]
        tasks.append(
            {
                "agent_type": agent_types[idx % len(agent_types)],
                "priority": priorities[idx % len(priorities)],
                "description": f"demo-seed-{seed}-task-{idx:02d}",
                "input_data": {
                    "plugin_domain": domain,
                    "demo_mode": True,
                    "seed": seed,
                    "index": idx,
                },
                "max_retries": 3,
            }
        )
    return tasks


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any] | str]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.getcode(), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return exc.code, detail
    except urllib.error.URLError as exc:
        return 0, str(exc)


def login(cfg: Config) -> str:
    code, payload = http_json(
        "POST",
        f"{cfg.api_base}/api/v1/auth/login",
        payload={"email": cfg.admin_email, "password": cfg.admin_password},
    )
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"login_failed_http_{code}")
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("login_succeeded_without_token")
    return token


def create_tasks(cfg: Config, token: str) -> list[str]:
    headers = {"Authorization": f"Bearer {token}"}
    task_ids: list[str] = []
    for payload in deterministic_workload(cfg.seed):
        code, body = http_json(
            "POST",
            f"{cfg.api_base}/api/v1/tasks/",
            payload=payload,
            headers=headers,
        )
        if code != 200 or not isinstance(body, dict):
            continue
        task_id = str(body.get("task_id") or "")
        if task_id:
            task_ids.append(task_id)
    return task_ids


def collect_statuses(cfg: Config, token: str, task_ids: list[str]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    started = time.time()
    timeline: list[dict[str, Any]] = []
    latest: dict[str, str] = {}

    while True:
        counts: dict[str, int] = {}
        for task_id in task_ids:
            code, payload = http_json(
                "GET",
                f"{cfg.api_base}/api/v1/tasks/{task_id}",
                headers=headers,
            )
            if code != 200 or not isinstance(payload, dict):
                latest[task_id] = f"http_{code}"
                counts[latest[task_id]] = counts.get(latest[task_id], 0) + 1
                continue
            status = str(payload.get("status") or "unknown")
            latest[task_id] = status
            counts[status] = counts.get(status, 0) + 1

        timeline.append({"at": utc_iso(), "counts": counts})

        terminal = sum(
            counts.get(name, 0)
            for name in ("completed", "failed", "cancelled", "timed_out")
        )
        if terminal >= len(task_ids):
            break
        if (time.time() - started) >= cfg.timeout_seconds:
            break
        time.sleep(cfg.poll_interval_seconds)

    return {"timeline": timeline, "final": latest}


def collect_replay(cfg: Config, token: str, task_ids: list[str]) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        state_code, state_response = http_json(
            "GET",
            f"{cfg.api_base}/api/v1/tasks/{task_id}/replay/state",
            headers=headers,
        )
        state_payload = state_response if isinstance(state_response, dict) else {"error": state_response}

        replay_payload: dict[str, Any] = {}
        if state_code == 200 and state_payload.get("replayable") is True:
            replay_code, replay_response = http_json(
                "GET",
                f"{cfg.api_base}/api/v1/tasks/{task_id}/replay",
                headers=headers,
            )
            if replay_code == 200 and isinstance(replay_response, dict):
                replay_payload = replay_response
            else:
                replay_payload = {"error": replay_response, "status": replay_code}

        rows.append(
            {
                "task_id": task_id,
                "state": state_payload,
                "replay": replay_payload,
            }
        )
    return rows


def run(cfg: Config) -> tuple[Path, bool]:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = cfg.output_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-demo-seeded-workload.json"
    health_code, health_payload = http_json("GET", f"{cfg.api_base}/health/ready")
    if health_code != 200 or not isinstance(health_payload, dict):
        raise RuntimeError(f"health_ready_failed_http_{health_code}")

    token = login(cfg)
    task_ids = create_tasks(cfg, token)
    statuses = collect_statuses(cfg, token, task_ids)
    replay_rows = collect_replay(cfg, token, task_ids)
    runtime_code, runtime_overview = http_json(
        "GET",
        f"{cfg.api_base}/health/runtime-overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    if runtime_code != 200 or not isinstance(runtime_overview, dict):
        raise RuntimeError(f"runtime_overview_failed_http_{runtime_code}")

    final_statuses = statuses.get("final", {})
    non_terminal = [
        task_id
        for task_id, status in final_statuses.items()
        if status not in {"completed", "failed", "cancelled", "timed_out"}
    ]
    report_status = "pass" if not non_terminal else "bounded_timeout"

    report = {
        "generated_at": utc_iso(),
        "seed": cfg.seed,
        "task_count": len(task_ids),
        "task_ids": task_ids,
        "status": statuses,
        "replay": replay_rows,
        "runtime_overview": runtime_overview,
        "report_status": report_status,
        "incomplete_tasks": non_terminal,
        "note": "Deterministic demo workload evidence artifact",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report_path, not non_terminal


def build_config(args: argparse.Namespace) -> Config:
    env_values = parse_env_file(Path(args.env_file))
    api_base = env_values.get("API_BASE_URL", "http://localhost:8000")
    admin_email = env_values.get("ADMIN_EMAIL", "admin@aura.local")
    admin_password = env_values.get("ADMIN_PASSWORD", "admin123")
    return Config(
        api_base=api_base,
        admin_email=admin_email,
        admin_password=admin_password,
        seed=args.seed,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
        output_dir=Path(args.output_dir),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic seeded demo workload")
    parser.add_argument("--env-file", default=".env.demo", help="Environment file used for admin credentials")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--output-dir", default="evidence/demo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = build_config(args)

    report_path, passed = run(cfg)
    if passed:
        print(f"[PASS] demo evidence written: {report_path}")
    else:
        print(f"[FAIL] demo evidence captured with incomplete tasks: {report_path}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
