"""Thin AURA command facade over existing runtime infrastructure."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


TERMINAL_TASK_STATES = {"completed", "failed", "cancelled", "timed_out"}
ACTIVE_TASK_STATES = {"created", "queued", "started", "running"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return payload


def _read_env(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(64 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _trim(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


@dataclass(frozen=True)
class FacadeConfig:
    aura_root: Path
    workspace_root: Path
    env_file: Path
    db_path: Path
    api_base: str
    request_timeout_seconds: float = 20.0


class AuraFacade:
    """Routes facade commands to already-existing runtime surfaces."""

    def __init__(
        self,
        config: FacadeConfig,
        *,
        shell_runner: Any | None = None,
        http_factory: Any | None = None,
    ):
        self._cfg = config
        self._shell_runner = shell_runner or self._default_shell_runner
        self._http_factory = http_factory or self._default_http_factory

    def execute(self, args: argparse.Namespace) -> dict[str, Any]:
        command = str(args.command or "").strip().lower()
        if command == "start":
            return self.start(args)
        if command == "learn":
            return self.learn(args)
        if command == "resume":
            return self.resume(args)
        if command == "status":
            return self.status(args)
        if command == "shutdown":
            return self.shutdown(args)
        raise RuntimeError(f"Unsupported command: {command}")

    def start(self, args: argparse.Namespace) -> dict[str, Any]:
        start_script = self._cfg.aura_root / "scripts" / "aura_start.sh"
        if not start_script.exists():
            raise RuntimeError(f"Missing startup script: {start_script}")

        command = [
            str(start_script),
            "--env-file",
            str(self._cfg.env_file),
            "--wait-seconds",
            str(int(args.wait_seconds)),
        ]
        if bool(args.skip_bootstrap):
            command.append("--skip-bootstrap")
        if bool(args.validate):
            command.append("--validate")
        if bool(args.no_build):
            command.append("--no-build")

        run = self._shell_runner(command, cwd=self._cfg.aura_root)
        if run.returncode != 0:
            failure_payload = {
                "classification": "FAIL_CLOSED",
                "reason": "startup_script_failed",
                "exit_code": run.returncode,
                "stdout": _trim(run.stdout),
                "stderr": _trim(run.stderr),
            }
            checkpoint_id = self._record_checkpoint(
                command_name="start",
                payload=failure_payload,
                status="failed",
            )
            raise RuntimeError(
                f"Runtime startup failed (checkpoint={checkpoint_id}): "
                f"exit={run.returncode} stderr={_trim(run.stderr, 320)}"
            )

        auth = self._login()
        runtime_overview = self._api_json(
            method="GET",
            path="/health/runtime-overview",
            token=auth["token"],
        )
        queue_stats = self._api_json(
            method="GET",
            path="/api/v1/tasks/queue/stats",
            token=auth["token"],
        )

        result = {
            "classification": "PASS",
            "command": "start",
            "started_at": _utc_now_iso(),
            "runtime": {
                "operational": runtime_overview.get("classification", {}).get("operational", "unknown"),
                "determinism": runtime_overview.get("classification", {}).get("determinism", "unknown"),
                "queue": queue_stats,
            },
            "auth": {
                "email": auth["email"],
            },
            "startup_script": {
                "path": str(start_script),
                "exit_code": run.returncode,
            },
        }
        checkpoint_id = self._record_checkpoint(
            command_name="start",
            payload=result,
            status="completed",
        )
        result["checkpoint_id"] = checkpoint_id
        return result

    def learn(self, args: argparse.Namespace) -> dict[str, Any]:
        platform = str(args.platform or "").strip().lower()
        if not platform:
            raise RuntimeError("learn requires <platform>")

        track_b = self._load_track_b_control_plane()
        auth = self._login()

        input_data = {
            "track": "B",
            "ownership": "track_b",
            "mode": "discovery_only",
            "workflow_kind": "track_b_discovery",
            "platform": platform,
            "track_b_stage": "DISCOVERED",
            "control_plane_assets": track_b["asset_paths"],
            "control_plane_sha256": track_b["asset_fingerprints"],
            "shared_core_references": track_b["shared_core_references"],
            "forbidden_actions": track_b["forbidden_actions"],
        }
        payload = {
            "agent_type": "learning",
            "priority": str(args.priority),
            "description": f"Track B discovery session for {platform}",
            "requested_by": auth["email"],
            "input_data": input_data,
        }

        created = self._api_json(
            method="POST",
            path="/api/v1/tasks/",
            token=auth["token"],
            json_body=payload,
        )
        task_id = str(created.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError("Task creation returned empty task_id")

        detail = self._api_json(
            method="GET",
            path=f"/api/v1/tasks/{task_id}",
            token=auth["token"],
        )
        replay_state = self._api_json(
            method="GET",
            path=f"/api/v1/tasks/{task_id}/replay/state",
            token=auth["token"],
        )

        result = {
            "classification": "PASS",
            "command": "learn",
            "created_at": _utc_now_iso(),
            "platform": platform,
            "task_id": task_id,
            "task_status": detail.get("status", "unknown"),
            "replay_state": replay_state,
            "track_b": {
                "mode": "DISCOVERY_ONLY",
                "control_plane_assets": track_b["asset_paths"],
            },
        }
        checkpoint_id = self._record_checkpoint(
            command_name="learn",
            payload=result,
            status="completed",
        )
        result["checkpoint_id"] = checkpoint_id
        return result

    def resume(self, args: argparse.Namespace) -> dict[str, Any]:
        auth = self._login()
        task_id = str(args.task_id or "").strip()

        if not task_id:
            listing = self._api_json(
                method="GET",
                path="/api/v1/tasks/",
                token=auth["token"],
                params={"agent_type": "learning", "page": 1, "limit": int(args.limit)},
            )
            tasks = listing.get("tasks", [])
            if not isinstance(tasks, list) or not tasks:
                checkpoint = self._latest_cli_checkpoint()
                if checkpoint is None:
                    raise RuntimeError("No learning task found to resume")
                return {
                    "classification": "ADVISORY_ONLY",
                    "command": "resume",
                    "mode": "checkpoint_only",
                    "checkpoint": checkpoint,
                }
            latest = tasks[0] if isinstance(tasks[0], dict) else {}
            task_id = str(latest.get("id") or "").strip()

        if not task_id:
            raise RuntimeError("Unable to resolve resume task_id")

        detail = self._api_json(
            method="GET",
            path=f"/api/v1/tasks/{task_id}",
            token=auth["token"],
        )
        replay_state = self._api_json(
            method="GET",
            path=f"/api/v1/tasks/{task_id}/replay/state",
            token=auth["token"],
        )

        replay_payload: dict[str, Any] = {}
        if bool(args.include_replay) and bool(replay_state.get("replayable", False)):
            replay_payload = self._api_json(
                method="GET",
                path=f"/api/v1/tasks/{task_id}/replay",
                token=auth["token"],
            )

        status = str(detail.get("status") or "unknown").lower()
        state = "active" if status in ACTIVE_TASK_STATES else "terminal"
        result = {
            "classification": "PASS" if state == "active" else "ADVISORY_ONLY",
            "command": "resume",
            "task_id": task_id,
            "task_status": status,
            "session_state": state,
            "detail": detail,
            "replay_state": replay_state,
            "replay": replay_payload,
        }
        checkpoint_id = self._record_checkpoint(
            command_name="resume",
            payload={
                "task_id": task_id,
                "task_status": status,
                "session_state": state,
                "replayable": bool(replay_state.get("replayable", False)),
            },
            status="completed",
        )
        result["checkpoint_id"] = checkpoint_id
        return result

    def status(self, args: argparse.Namespace) -> dict[str, Any]:
        auth = self._login()
        runtime_overview = self._api_json(
            method="GET",
            path="/health/runtime-overview",
            token=auth["token"],
        )
        queue_stats = self._api_json(
            method="GET",
            path="/api/v1/tasks/queue/stats",
            token=auth["token"],
        )
        running_agents = self._api_json(
            method="GET",
            path="/api/v1/agents/running",
            token=auth["token"],
        )
        learning_tasks = self._api_json(
            method="GET",
            path="/api/v1/tasks/",
            token=auth["token"],
            params={"agent_type": "learning", "page": 1, "limit": int(args.limit)},
        )
        boundary = self._load_track_boundary()

        tasks = learning_tasks.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []
        active_sessions = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_status = str(task.get("status") or "unknown").lower()
            stage = "DISCOVERED"
            input_data = task.get("input_data", {})
            if isinstance(input_data, dict):
                stage = str(input_data.get("track_b_stage") or "DISCOVERED")
            active_sessions.append(
                {
                    "task_id": str(task.get("id") or ""),
                    "status": task_status,
                    "stage": stage,
                    "platform": str(input_data.get("platform") or ""),
                    "ownership": "track_b",
                }
            )

        result = {
            "classification": "PASS",
            "command": "status",
            "generated_at": _utc_now_iso(),
            "runtime_health": runtime_overview.get("classification", {}),
            "queue": queue_stats,
            "active_agents": running_agents.get("agents", []),
            "active_sessions": active_sessions,
            "ownership": {
                "track_a_domains": boundary.get("track_a_owned_domains", []),
                "track_b_domains": boundary.get("track_b_owned_domains", []),
                "shared_domains": boundary.get("shared_domains", []),
            },
        }
        checkpoint_id = self._record_checkpoint(
            command_name="status",
            payload={
                "runtime_health": result["runtime_health"],
                "active_agent_count": len(result["active_agents"]),
                "active_session_count": len(result["active_sessions"]),
            },
            status="completed",
        )
        result["checkpoint_id"] = checkpoint_id
        return result

    def shutdown(self, args: argparse.Namespace) -> dict[str, Any]:
        auth = self._login()
        killed_agents: list[str] = []

        running = self._api_json(
            method="GET",
            path="/api/v1/agents/running",
            token=auth["token"],
        )
        for item in running.get("agents", []) if isinstance(running.get("agents"), list) else []:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or "").strip()
            if not agent_id:
                continue
            self._api_json(
                method="DELETE",
                path=f"/api/v1/agents/{agent_id}",
                token=auth["token"],
            )
            killed_agents.append(agent_id)

        compose_cmd = [
            "docker",
            "compose",
            "stop",
            "aura-dashboard",
            "aura-core",
            "ws-server",
            "llm-gateway",
        ]
        run = self._shell_runner(compose_cmd, cwd=self._cfg.aura_root)
        if run.returncode != 0:
            failure = {
                "classification": "FAIL_CLOSED",
                "reason": "docker_compose_stop_failed",
                "exit_code": run.returncode,
                "stdout": _trim(run.stdout),
                "stderr": _trim(run.stderr),
                "killed_agents": killed_agents,
            }
            checkpoint_id = self._record_checkpoint(
                command_name="shutdown",
                payload=failure,
                status="failed",
            )
            raise RuntimeError(
                f"Shutdown failed (checkpoint={checkpoint_id}): "
                f"exit={run.returncode} stderr={_trim(run.stderr, 320)}"
            )

        result = {
            "classification": "PASS",
            "command": "shutdown",
            "stopped_at": _utc_now_iso(),
            "killed_agents": killed_agents,
            "compose_exit_code": run.returncode,
        }
        checkpoint_id = self._record_checkpoint(
            command_name="shutdown",
            payload=result,
            status="completed",
        )
        result["checkpoint_id"] = checkpoint_id
        return result

    def _record_checkpoint(
        self,
        *,
        command_name: str,
        payload: dict[str, Any],
        status: str,
    ) -> str:
        recorder_cls = self._load_task_recorder_class()
        task_id = f"aura-cli-{command_name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        self._cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        recorder = recorder_cls(str(self._cfg.db_path))
        recorder.start_task(
            task_id=task_id,
            agent_type="aura_cli",
            seed=42,
            model_version="gpt-4o-2024-08-06",
            rules_path=str(self._track_b_root()),
            input_data={
                "command": command_name,
                "created_at": _utc_now_iso(),
                "payload": payload,
            },
        )
        recorder.record_execution_step(
            task_id,
            {
                "seq": 1,
                "step": "facade_command_completed",
                "details": {
                    "command": command_name,
                    "status": status,
                },
            },
        )
        finalized = recorder.finalize(
            task_id,
            {
                "status": status,
                "command": command_name,
                "payload": payload,
            },
        )
        if not finalized:
            raise RuntimeError(f"Failed to finalize checkpoint for command={command_name}")
        return task_id

    def _load_task_recorder_class(self) -> Any:
        # Prefer normal import path when running in the full Python 3.12 stack.
        try:
            from aura_sdk.replay.recorder import TaskRecorder as recorder_cls  # type: ignore

            return recorder_cls
        except Exception:
            pass

        # Fallback: load the same recorder implementation file directly.
        recorder_path = (
            self._cfg.aura_root
            / "workspace"
            / "aura-sdk"
            / "src"
            / "aura_sdk"
            / "replay"
            / "recorder.py"
        )
        if not recorder_path.exists():
            raise RuntimeError(f"TaskRecorder implementation not found: {recorder_path}")

        spec = importlib.util.spec_from_file_location("aura_task_recorder_runtime", recorder_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load TaskRecorder spec from {recorder_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        recorder_cls = getattr(module, "TaskRecorder", None)
        if recorder_cls is None:
            raise RuntimeError(f"TaskRecorder symbol missing in {recorder_path}")
        return recorder_cls

    def _latest_cli_checkpoint(self) -> dict[str, Any] | None:
        if not self._cfg.db_path.exists():
            return None
        with sqlite3.connect(self._cfg.db_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                """
                SELECT task_id, agent_type, created_at, output_json, recording_state
                FROM task_logs
                WHERE agent_type = 'aura_cli'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        output = {}
        try:
            output = json.loads(str(row["output_json"] or "{}"))
        except Exception:
            output = {}
        return {
            "task_id": str(row["task_id"] or ""),
            "recording_state": str(row["recording_state"] or ""),
            "created_at": int(row["created_at"] or 0),
            "output": output,
        }

    def _login(self) -> dict[str, str]:
        env_values = _read_env(self._cfg.env_file)
        email = env_values.get("ADMIN_EMAIL", "admin@aura.local")
        password = env_values.get("ADMIN_PASSWORD", "admin123")
        payload = {"email": email, "password": password}

        with self._http_factory() as client:
            response = client.post(
                f"{self._cfg.api_base}/api/v1/auth/login",
                json=payload,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Authentication failed: HTTP {response.status_code} body={_trim(response.text, 320)}"
            )
        body = response.json()
        token = str(body.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Authentication succeeded but no access_token returned")
        return {"token": token, "email": email}

    def _api_json(
        self,
        *,
        method: str,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._cfg.api_base}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        with self._http_factory() as client:
            response = client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_body,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"API call failed: {method.upper()} {path} -> HTTP {response.status_code} "
                f"body={_trim(response.text, 480)}"
            )
        body = response.json()
        if isinstance(body, dict):
            return body
        raise RuntimeError(f"Expected JSON object for {method.upper()} {path}")

    def _load_track_b_control_plane(self) -> dict[str, Any]:
        root = self._track_b_root()
        files = {
            "architecture_plan.md": root / "architecture_plan.md",
            "track_boundary_report.json": root / "track_boundary_report.json",
            "learning_progress_model.json": root / "learning_progress_model.json",
            "readiness_assessment.json": root / "readiness_assessment.json",
        }
        missing = [name for name, path in files.items() if not path.exists()]
        if missing:
            raise RuntimeError(f"Track B control-plane assets missing: {', '.join(missing)}")

        boundary = _read_json(files["track_boundary_report.json"])
        readiness = _read_json(files["readiness_assessment.json"])

        return {
            "asset_paths": {name: str(path) for name, path in files.items()},
            "asset_fingerprints": {name: _sha256_file(path) for name, path in files.items()},
            "shared_core_references": boundary.get("shared_core_references", {}),
            "forbidden_actions": readiness.get("forbidden_actions", []),
        }

    def _load_track_boundary(self) -> dict[str, Any]:
        path = self._track_b_root() / "track_boundary_report.json"
        if not path.exists():
            return {}
        return _read_json(path)

    def _track_b_root(self) -> Path:
        return self._cfg.workspace_root / "docs" / "operations" / "transport" / "tracks" / "upstream-learning"

    def _default_http_factory(self) -> httpx.Client:
        return httpx.Client(timeout=self._cfg.request_timeout_seconds)

    @staticmethod
    def _default_shell_runner(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )


def _default_config() -> FacadeConfig:
    aura_root = Path(__file__).resolve().parents[3]
    workspace_root = aura_root.parent
    env_file = aura_root / ".env"
    db_path = aura_root / "data" / "aura.db"
    return FacadeConfig(
        aura_root=aura_root,
        workspace_root=workspace_root,
        env_file=env_file,
        db_path=db_path,
        api_base="http://localhost:8000",
    )


def build_parser() -> argparse.ArgumentParser:
    cfg = _default_config()
    parser = argparse.ArgumentParser(
        prog="aura",
        description="Thin AURA facade over existing runtime infrastructure.",
    )
    parser.add_argument(
        "--api-base",
        default=cfg.api_base,
        help="Core API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--env-file",
        default=str(cfg.env_file),
        help="Path to AURA .env file (default: %(default)s)",
    )
    parser.add_argument(
        "--db-path",
        default=str(cfg.db_path),
        help="Path to replay/checkpoint SQLite DB (default: %(default)s)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start runtime services via existing startup script.")
    start.add_argument("--wait-seconds", type=int, default=120)
    start.add_argument("--skip-bootstrap", action="store_true")
    start.add_argument("--validate", action="store_true")
    start.add_argument("--no-build", action="store_true")

    learn = sub.add_parser("learn", help="Create a Track B discovery learning session.")
    learn.add_argument("platform", help="Target platform (example: sc7280)")
    learn.add_argument(
        "--priority",
        default="P1",
        choices=["P0", "P1", "P2"],
        help="Task priority for learning session.",
    )

    resume = sub.add_parser("resume", help="Resume latest or selected learning session.")
    resume.add_argument("--task-id", default="", help="Explicit learning task id to resume.")
    resume.add_argument("--include-replay", action="store_true", help="Include replay payload when available.")
    resume.add_argument("--limit", type=int, default=20, help="Task lookup window for latest resume.")

    status = sub.add_parser("status", help="Show runtime health, active sessions, and ownership state.")
    status.add_argument("--limit", type=int, default=20, help="Number of latest learning tasks to show.")

    sub.add_parser("shutdown", help="Gracefully stop agents and runtime services.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = _default_config()
    runtime_cfg = FacadeConfig(
        aura_root=cfg.aura_root,
        workspace_root=cfg.workspace_root,
        env_file=Path(str(args.env_file)).resolve(),
        db_path=Path(str(args.db_path)).resolve(),
        api_base=str(args.api_base).rstrip("/"),
        request_timeout_seconds=20.0,
    )
    facade = AuraFacade(runtime_cfg)

    try:
        payload = facade.execute(args)
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
