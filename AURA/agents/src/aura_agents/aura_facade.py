"""Thin AURA command facade over existing runtime infrastructure."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
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
REQUIRED_SESSION_IDENTITY_FIELDS = ("track", "ownership", "session_kind")
TRACK_B_EXECUTION_STAGES = (
    "DISCOVERED",
    "INDEXED",
    "STATIC_ANALYZED",
    "EQUIVALENCE_MAPPED",
    "DEPENDENCIES_BOUND",
    "CONFLICTS_EVALUATED",
    "DECISION_FINALIZED",
    "REPORT_GENERATED",
    "READINESS_GATED",
)
UPSTREAMING_COMPONENT_TYPES = (
    "function",
    "driver",
    "dt_node",
    "mixer_control",
    "dai_link",
    "soundwire_endpoint",
    "apr_service",
    "dsp_graph_component",
)
RUNTIME_SENSITIVE_COMPONENT_TYPES = (
    "mixer_control",
    "dai_link",
    "soundwire_endpoint",
    "apr_service",
    "dsp_graph_component",
)
RUNTIME_EVIDENCE_REF_RE = re.compile(r"^(runtime|m7):[a-z0-9_.-]+:[a-z0-9_.:/-]+$", re.IGNORECASE)
DEFAULT_TRACK_B_SOURCE_ROOTS = (
    "sound/soc/qcom",
    "arch/arm64/boot/dts/qcom",
    "Documentation/devicetree/bindings/sound",
)
DEFAULT_TRACK_B_INCLUDE_PATTERNS = (
    "*.c",
    "*.h",
    "*.dts",
    "*.dtsi",
    "*.yaml",
    "*.yml",
    "Kconfig",
    "Makefile",
    "*.mk",
)
DEFAULT_TRACK_B_EXCLUDE_PATTERNS = (
    ".git",
    ".git/*",
)


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


def _is_commit_sha(value: str) -> bool:
    text = str(value or "").strip().lower()
    if len(text) < 7 or len(text) > 64:
        return False
    for char in text:
        if char not in "0123456789abcdef":
            return False
    return True


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

    @staticmethod
    def _normalize_identity_filters(
        *,
        track: str = "",
        ownership: str = "",
        session_kind: str = "",
        platform: str = "",
    ) -> dict[str, str]:
        return {
            "track": str(track or "").strip().upper(),
            "ownership": str(ownership or "").strip().lower(),
            "session_kind": str(session_kind or "").strip().lower(),
            "platform": str(platform or "").strip().lower(),
        }

    @staticmethod
    def _identity_matches(identity: dict[str, str], filters: dict[str, str]) -> bool:
        for key, expected in filters.items():
            if not expected:
                continue
            if identity.get(key, "") != expected:
                return False
        return True

    @staticmethod
    def _require_identity_filters(
        *,
        filters: dict[str, str],
        command: str,
        required_fields: tuple[str, ...],
    ) -> None:
        missing = [name for name in required_fields if not str(filters.get(name, "")).strip()]
        if missing:
            raise RuntimeError(
                f"{command} fail-closed: missing explicit identity filters: {', '.join(missing)}"
            )

    def _task_identity(self, task: dict[str, Any]) -> dict[str, str]:
        input_data = task.get("input_data", {})
        if not isinstance(input_data, dict):
            input_data = {}
        return self._normalize_identity_filters(
            track=str(input_data.get("track", "")),
            ownership=str(input_data.get("ownership", "")),
            session_kind=str(input_data.get("workflow_kind", "")),
            platform=str(input_data.get("platform", "")),
        )

    def _assert_identity_metadata(
        self,
        *,
        task: dict[str, Any],
        context: str,
    ) -> dict[str, str]:
        identity = self._task_identity(task)
        missing = [name for name in REQUIRED_SESSION_IDENTITY_FIELDS if not identity.get(name, "")]
        if missing:
            raise RuntimeError(
                f"{context} fail-closed: task missing ownership/session identity metadata: "
                f"{', '.join(missing)}"
            )
        return identity

    def _resolve_session_task(
        self,
        *,
        token: str,
        task_id: str,
        filters: dict[str, str],
        limit: int,
        command: str,
    ) -> dict[str, Any]:
        normalized_task_id = str(task_id or "").strip()
        if normalized_task_id:
            detail = self._api_json(
                method="GET",
                path=f"/api/v1/tasks/{normalized_task_id}",
                token=token,
            )
            identity = self._assert_identity_metadata(task=detail, context=command)
            if not self._identity_matches(identity, filters):
                raise RuntimeError(
                    f"{command} fail-closed: explicit identity filters mismatch task_id={normalized_task_id}"
                )
            return detail

        self._require_identity_filters(
            filters=filters,
            command=command,
            required_fields=REQUIRED_SESSION_IDENTITY_FIELDS,
        )
        listing = self._api_json(
            method="GET",
            path="/api/v1/tasks/",
            token=token,
            params={"page": 1, "limit": int(limit)},
        )
        tasks = listing.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []

        matches: list[dict[str, Any]] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            identity = self._task_identity(task)
            if any(not identity.get(name, "") for name in REQUIRED_SESSION_IDENTITY_FIELDS):
                continue
            if self._identity_matches(identity, filters):
                matches.append(task)

        if not matches:
            raise RuntimeError(
                f"{command} fail-closed: no session matches explicit ownership/session identity filters"
            )
        if len(matches) > 1:
            ids = [str(item.get("id", "")) for item in matches]
            raise RuntimeError(
                f"{command} fail-closed: ambiguous session identity matches multiple tasks: {ids}"
            )

        resolved_task_id = str(matches[0].get("id", "")).strip()
        if not resolved_task_id:
            raise RuntimeError(f"{command} fail-closed: resolved task missing id")

        detail = self._api_json(
            method="GET",
            path=f"/api/v1/tasks/{resolved_task_id}",
            token=token,
        )
        detail_identity = self._assert_identity_metadata(task=detail, context=command)
        if not self._identity_matches(detail_identity, filters):
            raise RuntimeError(
                f"{command} fail-closed: resolved task identity drift detected for task_id={resolved_task_id}"
        )
        return detail

    @staticmethod
    def _git_read(*, repository_root: Path, args: list[str], field: str) -> str:
        run = subprocess.run(
            ["git", "-C", str(repository_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            stderr = _trim(str(run.stderr or ""), 320)
            raise RuntimeError(
                f"learn fail-closed: unable to read {field} from {repository_root}: {stderr}"
            )
        value = str(run.stdout or "").strip()
        if not value:
            raise RuntimeError(
                f"learn fail-closed: git returned empty {field} for {repository_root}"
            )
        return value

    def _build_track_b_corpus(
        self,
        *,
        corpus_id: str,
        corpus_role: str,
        repository_root: str,
        remote: str,
        branch: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        corpus_id_text = str(corpus_id or "").strip()
        if not corpus_id_text:
            raise RuntimeError(f"learn fail-closed: {corpus_role} corpus_id must be non-empty")
        role = str(corpus_role or "").strip().lower()
        if role not in {"downstream", "upstream"}:
            raise RuntimeError(f"learn fail-closed: unsupported corpus_role={corpus_role!r}")
        repo_root = Path(str(repository_root or "")).resolve()
        if not repo_root.exists() or not repo_root.is_dir():
            raise RuntimeError(
                f"learn fail-closed: {role} repository root does not exist: {repository_root}"
            )

        resolved_remote = str(remote or "").strip()
        if not resolved_remote:
            resolved_remote = self._git_read(
                repository_root=repo_root,
                args=["config", "--get", "remote.origin.url"],
                field=f"{role}.revision.remote",
            )
        resolved_branch = str(branch or "").strip()
        if not resolved_branch:
            resolved_branch = self._git_read(
                repository_root=repo_root,
                args=["rev-parse", "--abbrev-ref", "HEAD"],
                field=f"{role}.revision.branch",
            )
        resolved_commit = str(commit_sha or "").strip().lower()
        if not resolved_commit:
            resolved_commit = self._git_read(
                repository_root=repo_root,
                args=["rev-parse", "HEAD"],
                field=f"{role}.revision.commit_sha",
            ).lower()
        if not _is_commit_sha(resolved_commit):
            raise RuntimeError(
                f"learn fail-closed: {role}.revision.commit_sha must be hexadecimal commit SHA"
            )

        return {
            "corpus_id": corpus_id_text,
            "corpus_role": role,
            "repository_root": str(repo_root),
            "revision": {
                "remote": resolved_remote,
                "branch": resolved_branch,
                "commit_sha": resolved_commit,
            },
            "source_roots": list(DEFAULT_TRACK_B_SOURCE_ROOTS),
            "include_patterns": list(DEFAULT_TRACK_B_INCLUDE_PATTERNS),
            "exclude_patterns": list(DEFAULT_TRACK_B_EXCLUDE_PATTERNS),
        }

    def _build_track_b_corpora(self, args: argparse.Namespace) -> list[dict[str, Any]]:
        downstream_root = str(args.downstream_root or "").strip() or str(
            self._cfg.workspace_root / "track_b_corpora" / "audio-kernel-ar"
        )
        upstream_root = str(args.upstream_root or "").strip() or str(
            self._cfg.workspace_root / "track_b_corpora" / "linux-next"
        )

        downstream = self._build_track_b_corpus(
            corpus_id=str(args.downstream_corpus_id or "audio-kernel-ar"),
            corpus_role="downstream",
            repository_root=downstream_root,
            remote=str(args.downstream_remote or ""),
            branch=str(args.downstream_branch or ""),
            commit_sha=str(args.downstream_commit or ""),
        )
        upstream = self._build_track_b_corpus(
            corpus_id=str(args.upstream_corpus_id or "linux-next"),
            corpus_role="upstream",
            repository_root=upstream_root,
            remote=str(args.upstream_remote or ""),
            branch=str(args.upstream_branch or ""),
            commit_sha=str(args.upstream_commit or ""),
        )
        return [downstream, upstream]

    @staticmethod
    def _normalize_track_b_target_stage(raw: str) -> str:
        stage = str(raw or "").strip().upper()
        if not stage:
            return "STATIC_ANALYZED"
        if stage not in TRACK_B_EXECUTION_STAGES:
            raise RuntimeError(
                f"learn fail-closed: unsupported target stage {stage!r}; allowed={TRACK_B_EXECUTION_STAGES}"
            )
        return stage

    @staticmethod
    def _requires_upstreaming_request(target_stage: str) -> bool:
        stage = str(target_stage or "").strip().upper()
        if stage not in TRACK_B_EXECUTION_STAGES:
            return False
        return TRACK_B_EXECUTION_STAGES.index(stage) > TRACK_B_EXECUTION_STAGES.index("STATIC_ANALYZED")

    @staticmethod
    def _build_upstreaming_request(args: argparse.Namespace) -> dict[str, Any]:
        component_kind = str(args.component_kind or "").strip().lower()
        component_name = str(args.component_name or "").strip()
        source_path = str(args.component_source_path or "").strip()
        line_start = int(args.component_line_start or 0)
        line_end = int(args.component_line_end or 0)
        request_id = str(args.upstreaming_request_id or "").strip()
        runtime_evidence_refs = [str(item).strip() for item in list(args.runtime_evidence_ref or []) if str(item).strip()]
        runtime_evidence_refs = sorted(set(runtime_evidence_refs))

        if not component_kind and not component_name and not source_path and not request_id and not runtime_evidence_refs:
            return {}
        if component_kind not in UPSTREAMING_COMPONENT_TYPES:
            raise RuntimeError(
                "learn fail-closed: --component-kind must be one of "
                + ", ".join(UPSTREAMING_COMPONENT_TYPES)
            )
        if not component_name:
            raise RuntimeError("learn fail-closed: --component-name is required when upstreaming request is provided")
        if not source_path:
            raise RuntimeError("learn fail-closed: --component-source-path is required for upstreaming request")
        if not request_id:
            raise RuntimeError("learn fail-closed: --upstreaming-request-id is required for upstreaming request")
        if line_start < 0 or line_end < 0:
            raise RuntimeError("learn fail-closed: component line values must be >= 0")
        if line_end and line_start and line_end < line_start:
            raise RuntimeError("learn fail-closed: --component-line-end must be >= --component-line-start")
        for index, ref in enumerate(runtime_evidence_refs):
            if not RUNTIME_EVIDENCE_REF_RE.match(ref):
                raise RuntimeError(
                    "learn fail-closed: --runtime-evidence-ref["
                    + str(index)
                    + "] must match '<runtime|m7>:<type>:<id>'"
                )
        runtime_evidence_required = component_kind in RUNTIME_SENSITIVE_COMPONENT_TYPES
        if runtime_evidence_required and not runtime_evidence_refs:
            raise RuntimeError(
                "learn fail-closed: --runtime-evidence-ref is required for runtime-sensitive component-kind "
                + component_kind
            )

        return {
            "request_id": request_id,
            "downstream_component": {
                "component_type": component_kind,
                "component_name": component_name,
                "source_path": source_path,
                "line_start": line_start,
                "line_end": line_end,
            },
            "runtime_evidence_required": runtime_evidence_required,
            "runtime_evidence_refs": runtime_evidence_refs,
        }

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
        readiness = track_b.get("readiness", {})
        go_no_go = str(readiness.get("go_no_go", "")).strip().upper()
        if go_no_go != "GO_DISCOVERY_ONLY":
            raise RuntimeError(
                f"learn fail-closed: readiness go/no-go prohibits discovery (go_no_go={go_no_go!r})"
            )
        scope_mode = str(readiness.get("scope_mode", "")).strip().upper()
        if scope_mode != "DISCOVERY_ONLY":
            raise RuntimeError(
                f"learn fail-closed: unsupported readiness scope_mode for Track B discovery ({scope_mode!r})"
            )
        hard_blockers = readiness.get("hard_blockers", [])
        if isinstance(hard_blockers, list) and hard_blockers:
            raise RuntimeError(
                f"learn fail-closed: readiness has hard blockers: {hard_blockers}"
            )
        corpora = self._build_track_b_corpora(args)
        target_stage = self._normalize_track_b_target_stage(str(args.target_stage or "STATIC_ANALYZED"))
        upstreaming_request = self._build_upstreaming_request(args)
        if self._requires_upstreaming_request(target_stage) and not upstreaming_request:
            raise RuntimeError(
                "learn fail-closed: upstreaming request is required when target stage is beyond STATIC_ANALYZED"
            )
        stage_execution_mode = (
            "m8_deterministic_upstreaming"
            if self._requires_upstreaming_request(target_stage)
            else "m6_deterministic_dual_corpus"
        )

        auth = self._login()

        input_data = {
            "track": "B",
            "ownership": "track_b",
            "mode": "discovery_only",
            "workflow_kind": "track_b_discovery",
            "platform": platform,
            "repository_root": str(self._cfg.workspace_root),
            "track_b_stage": "DISCOVERED",
            "track_b_initial_stage": "DISCOVERED",
            "track_b_target_stage": target_stage,
            "stage_execution_mode": stage_execution_mode,
            "control_plane_assets": track_b["asset_paths"],
            "control_plane_sha256": track_b["asset_fingerprints"],
            "shared_core_references": track_b["shared_core_references"],
            "forbidden_actions": track_b["forbidden_actions"],
            "track_b_readiness": readiness,
            "track_b_hard_blockers": hard_blockers if isinstance(hard_blockers, list) else [],
            "corpora": corpora,
        }
        if upstreaming_request:
            input_data["upstreaming_request"] = upstreaming_request
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
        filters = self._normalize_identity_filters(
            track=str(args.track or ""),
            ownership=str(args.ownership or ""),
            session_kind=str(args.session_kind or ""),
            platform=str(args.platform or ""),
        )
        detail = self._resolve_session_task(
            token=auth["token"],
            task_id=str(args.task_id or ""),
            filters=filters,
            limit=int(args.limit),
            command="resume",
        )
        task_id = str(detail.get("id") or args.task_id or "").strip()
        if not task_id:
            raise RuntimeError("resume fail-closed: resolved session has empty task id")
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
        scope = str(args.scope or "session").strip().lower()
        if scope not in {"session", "track", "all"}:
            raise RuntimeError(f"shutdown fail-closed: unsupported scope '{scope}'")

        killed_agents: list[str] = []

        running = self._api_json(
            method="GET",
            path="/api/v1/agents/running",
            token=auth["token"],
        )
        running_agents = running.get("agents", [])
        if not isinstance(running_agents, list):
            running_agents = []

        target_agents: list[dict[str, Any]] = []
        scoped_task_ids: list[str] = []
        track_filters = self._normalize_identity_filters(
            track=str(args.track or ""),
            ownership=str(args.ownership or ""),
            session_kind=str(args.session_kind or ""),
            platform=str(args.platform or ""),
        )

        if scope == "all":
            role = str(auth.get("role", "")).strip().lower()
            if role != "admin":
                raise RuntimeError("shutdown --scope all fail-closed: admin role required")
            target_agents = [agent for agent in running_agents if isinstance(agent, dict)]
        elif scope == "session":
            detail = self._resolve_session_task(
                token=auth["token"],
                task_id=str(args.task_id or ""),
                filters=track_filters,
                limit=int(args.limit),
                command="shutdown --scope session",
            )
            session_task_id = str(detail.get("id") or args.task_id or "").strip()
            if not session_task_id:
                raise RuntimeError("shutdown --scope session fail-closed: resolved task id missing")
            scoped_task_ids.append(session_task_id)
            target_agents = [
                agent
                for agent in running_agents
                if isinstance(agent, dict) and str(agent.get("task_id") or "").strip() == session_task_id
            ]
        else:  # scope == "track"
            self._require_identity_filters(
                filters=track_filters,
                command="shutdown --scope track",
                required_fields=("track", "ownership"),
            )
            for agent in running_agents:
                if not isinstance(agent, dict):
                    continue
                task_id = str(agent.get("task_id") or "").strip()
                if not task_id:
                    continue
                detail = self._api_json(
                    method="GET",
                    path=f"/api/v1/tasks/{task_id}",
                    token=auth["token"],
                )
                identity = self._assert_identity_metadata(
                    task=detail,
                    context=f"shutdown --scope track task_id={task_id}",
                )
                if self._identity_matches(identity, track_filters):
                    target_agents.append(agent)
                    scoped_task_ids.append(task_id)

        if not target_agents:
            advisory = {
                "classification": "ADVISORY_ONLY",
                "command": "shutdown",
                "scope": scope,
                "reason": "no_running_agents_match_scope",
                "stopped_at": _utc_now_iso(),
                "killed_agents": [],
                "services_stopped": False,
                "scoped_task_ids": sorted(set(scoped_task_ids)),
            }
            advisory_checkpoint = self._record_checkpoint(
                command_name="shutdown",
                payload=advisory,
                status="completed",
            )
            advisory["checkpoint_id"] = advisory_checkpoint
            return advisory

        for item in target_agents:
            agent_id = str(item.get("agent_id") or "").strip()
            if not agent_id:
                continue
            self._api_json(
                method="DELETE",
                path=f"/api/v1/agents/{agent_id}",
                token=auth["token"],
            )
            killed_agents.append(agent_id)

        compose_exit_code: int | None = None
        services_stopped = False
        if scope == "all":
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
            compose_exit_code = int(run.returncode)
            if run.returncode != 0:
                failure = {
                    "classification": "FAIL_CLOSED",
                    "reason": "docker_compose_stop_failed",
                    "scope": scope,
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
            services_stopped = True

        result = {
            "classification": "PASS",
            "command": "shutdown",
            "scope": scope,
            "stopped_at": _utc_now_iso(),
            "killed_agents": killed_agents,
            "services_stopped": services_stopped,
            "compose_exit_code": compose_exit_code,
            "scoped_task_ids": sorted(set(scoped_task_ids)),
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
        user = body.get("user", {})
        role = ""
        if isinstance(user, dict):
            role = str(user.get("role") or "").strip().lower()
        return {"token": token, "email": email, "role": role}

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
        hard_blockers = readiness.get("hard_blockers", [])
        if not isinstance(hard_blockers, list):
            hard_blockers = []
        readiness_payload = {
            "go_no_go": str(readiness.get("go_no_go", "")).strip().upper(),
            "scope_mode": str(readiness.get("scope_mode", "")).strip().upper(),
            "hard_blockers": [str(item).strip() for item in hard_blockers if str(item).strip()],
            "classification": str(readiness.get("classification", "")).strip(),
        }

        return {
            "asset_paths": {name: str(path) for name, path in files.items()},
            "asset_fingerprints": {name: _sha256_file(path) for name, path in files.items()},
            "shared_core_references": boundary.get("shared_core_references", {}),
            "forbidden_actions": readiness.get("forbidden_actions", []),
            "readiness": readiness_payload,
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
    learn.add_argument(
        "--downstream-root",
        default="",
        help=(
            "Downstream corpus repository root. Defaults to "
            "<workspace>/track_b_corpora/audio-kernel-ar."
        ),
    )
    learn.add_argument(
        "--upstream-root",
        default="",
        help=(
            "Upstream corpus repository root. Defaults to "
            "<workspace>/track_b_corpora/linux-next."
        ),
    )
    learn.add_argument(
        "--downstream-corpus-id",
        default="audio-kernel-ar",
        help="Downstream corpus identifier (default: %(default)s).",
    )
    learn.add_argument(
        "--upstream-corpus-id",
        default="linux-next",
        help="Upstream corpus identifier (default: %(default)s).",
    )
    learn.add_argument("--downstream-remote", default="", help="Optional downstream revision.remote override.")
    learn.add_argument("--downstream-branch", default="", help="Optional downstream revision.branch override.")
    learn.add_argument("--downstream-commit", default="", help="Optional downstream revision.commit_sha override.")
    learn.add_argument("--upstream-remote", default="", help="Optional upstream revision.remote override.")
    learn.add_argument("--upstream-branch", default="", help="Optional upstream revision.branch override.")
    learn.add_argument("--upstream-commit", default="", help="Optional upstream revision.commit_sha override.")
    learn.add_argument(
        "--target-stage",
        default="STATIC_ANALYZED",
        choices=list(TRACK_B_EXECUTION_STAGES),
        help="Track-B target stage for deterministic execution (default: %(default)s).",
    )
    learn.add_argument(
        "--upstreaming-request-id",
        default="",
        help="Required when target stage is beyond STATIC_ANALYZED.",
    )
    learn.add_argument(
        "--component-kind",
        default="",
        help=(
            "Downstream component kind for M8 upstreaming request "
            f"({', '.join(UPSTREAMING_COMPONENT_TYPES)})."
        ),
    )
    learn.add_argument(
        "--component-name",
        default="",
        help="Downstream component identifier (function/driver/DT node/etc).",
    )
    learn.add_argument(
        "--component-source-path",
        default="",
        help="Optional downstream source path to constrain deterministic matching.",
    )
    learn.add_argument(
        "--component-line-start",
        type=int,
        default=0,
        help="Optional downstream component line_start.",
    )
    learn.add_argument(
        "--component-line-end",
        type=int,
        default=0,
        help="Optional downstream component line_end.",
    )
    learn.add_argument(
        "--runtime-evidence-ref",
        action="append",
        default=[],
        help="Optional runtime evidence reference. Repeat flag for multiple references.",
    )

    resume = sub.add_parser("resume", help="Resume latest or selected learning session.")
    resume.add_argument("--task-id", default="", help="Explicit learning task id to resume.")
    resume.add_argument("--track", default="", help="Track filter (required unless --task-id is provided).")
    resume.add_argument("--ownership", default="", help="Ownership filter (required unless --task-id is provided).")
    resume.add_argument(
        "--session-kind",
        default="",
        help="Session kind filter mapped to task input_data.workflow_kind.",
    )
    resume.add_argument("--platform", default="", help="Optional platform filter for session identity.")
    resume.add_argument("--include-replay", action="store_true", help="Include replay payload when available.")
    resume.add_argument("--limit", type=int, default=20, help="Task lookup window for latest resume.")

    status = sub.add_parser("status", help="Show runtime health, active sessions, and ownership state.")
    status.add_argument("--limit", type=int, default=20, help="Number of latest learning tasks to show.")

    shutdown = sub.add_parser("shutdown", help="Gracefully stop scoped agents and optional services.")
    shutdown.add_argument(
        "--scope",
        default="session",
        choices=["session", "track", "all"],
        help="Shutdown scope: session, track, or all (admin-only).",
    )
    shutdown.add_argument("--task-id", default="", help="Session task id for --scope session.")
    shutdown.add_argument("--track", default="", help="Track filter for scoped shutdown.")
    shutdown.add_argument("--ownership", default="", help="Ownership filter for scoped shutdown.")
    shutdown.add_argument("--session-kind", default="", help="Optional workflow/session kind filter.")
    shutdown.add_argument("--platform", default="", help="Optional platform filter.")
    shutdown.add_argument("--limit", type=int, default=200, help="Task lookup window for session resolution.")
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
