"""Routing and parser tests for aura facade CLI."""

from __future__ import annotations

import argparse
import json
import subprocess

import pytest

from aura_agents import aura_facade


def _make_facade(tmp_path, monkeypatch):
    shell_calls: list[list[str]] = []

    def _shell_runner(command, *, cwd):
        shell_calls.append([str(item) for item in command])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    cfg = aura_facade.FacadeConfig(
        aura_root=tmp_path / "AURA",
        workspace_root=tmp_path,
        env_file=tmp_path / ".env",
        db_path=tmp_path / "aura.db",
        api_base="http://localhost:8000",
    )
    facade = aura_facade.AuraFacade(cfg, shell_runner=_shell_runner)
    monkeypatch.setattr(facade, "_record_checkpoint", lambda **_: "ckpt-test")
    return facade, shell_calls


def _resume_args(**overrides):
    base = {
        "task_id": "",
        "track": "",
        "ownership": "",
        "session_kind": "",
        "platform": "",
        "include_replay": False,
        "limit": 20,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _shutdown_args(**overrides):
    base = {
        "scope": "session",
        "task_id": "",
        "track": "",
        "ownership": "",
        "session_kind": "",
        "platform": "",
        "limit": 200,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parser_contains_required_commands():
    parser = aura_facade.build_parser()
    help_text = parser.format_help()
    for command in ("start", "learn", "resume", "status", "shutdown"):
        assert command in help_text


def test_main_routes_start_command(monkeypatch, capsys):
    called: dict[str, str] = {}

    class _FakeFacade:
        def __init__(self, _cfg):
            pass

        def execute(self, args):
            called["command"] = args.command
            return {"classification": "PASS", "command": args.command}

    monkeypatch.setattr(aura_facade, "AuraFacade", _FakeFacade)
    rc = aura_facade.main(["start", "--wait-seconds", "5"])
    assert rc == 0
    assert called["command"] == "start"
    out = json.loads(capsys.readouterr().out)
    assert out["classification"] == "PASS"
    assert out["command"] == "start"


def test_main_routes_learn_command(monkeypatch, capsys):
    called: dict[str, str] = {}

    class _FakeFacade:
        def __init__(self, _cfg):
            pass

        def execute(self, args):
            called["command"] = args.command
            called["platform"] = args.platform
            return {"classification": "PASS", "command": args.command, "platform": args.platform}

    monkeypatch.setattr(aura_facade, "AuraFacade", _FakeFacade)
    rc = aura_facade.main(["learn", "sc7280"])
    assert rc == 0
    assert called["command"] == "learn"
    assert called["platform"] == "sc7280"
    out = json.loads(capsys.readouterr().out)
    assert out["command"] == "learn"
    assert out["platform"] == "sc7280"


def test_main_returns_failure_code_on_exception(monkeypatch, capsys):
    class _FakeFacade:
        def __init__(self, _cfg):
            pass

        def execute(self, _args):
            raise RuntimeError("boom")

    monkeypatch.setattr(aura_facade, "AuraFacade", _FakeFacade)
    rc = aura_facade.main(["status"])
    assert rc == 1
    assert "[FAIL] boom" in capsys.readouterr().err


def test_resume_requires_explicit_identity_without_task_id(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )

    with pytest.raises(RuntimeError, match="missing explicit identity filters"):
        facade.resume(_resume_args())


def test_resume_fails_closed_on_ambiguous_identity(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = method, token, params, json_body
        if path == "/api/v1/tasks/":
            return {
                "tasks": [
                    {
                        "id": "task-a",
                        "input_data": {
                            "track": "B",
                            "ownership": "track_b",
                            "workflow_kind": "track_b_discovery",
                            "platform": "sc7280",
                        },
                    },
                    {
                        "id": "task-b",
                        "input_data": {
                            "track": "B",
                            "ownership": "track_b",
                            "workflow_kind": "track_b_discovery",
                            "platform": "sc7280",
                        },
                    },
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)

    with pytest.raises(RuntimeError, match="ambiguous session identity"):
        facade.resume(
            _resume_args(
                track="B",
                ownership="track_b",
                session_kind="track_b_discovery",
                platform="sc7280",
            )
        )


def test_resume_task_id_with_mismatched_identity_fails_closed(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = method, token, params, json_body
        if path == "/api/v1/tasks/task-1":
            return {
                "id": "task-1",
                "status": "running",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                    "workflow_kind": "track_b_discovery",
                },
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)

    with pytest.raises(RuntimeError, match="identity filters mismatch"):
        facade.resume(
            _resume_args(
                task_id="task-1",
                track="A",
                ownership="track_b",
                session_kind="track_b_discovery",
            )
        )


def test_resume_with_explicit_filters_resolves_single_session(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    calls: list[str] = []

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = method, token, params, json_body
        calls.append(path)
        if path == "/api/v1/tasks/":
            return {
                "tasks": [
                    {
                        "id": "task-nonmatch",
                        "input_data": {
                            "track": "A",
                            "ownership": "track_a",
                            "workflow_kind": "runtime_capture",
                        },
                    },
                    {
                        "id": "task-match",
                        "input_data": {
                            "track": "B",
                            "ownership": "track_b",
                            "workflow_kind": "track_b_discovery",
                            "platform": "sc7280",
                        },
                    },
                ]
            }
        if path == "/api/v1/tasks/task-match":
            return {
                "id": "task-match",
                "status": "running",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                    "workflow_kind": "track_b_discovery",
                    "platform": "sc7280",
                },
            }
        if path == "/api/v1/tasks/task-match/replay/state":
            return {"replayable": False}
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)
    result = facade.resume(
        _resume_args(
            track="B",
            ownership="track_b",
            session_kind="track_b_discovery",
            platform="sc7280",
        )
    )
    assert result["classification"] == "PASS"
    assert result["task_id"] == "task-match"
    assert "/api/v1/tasks/task-match" in calls


def test_shutdown_scope_all_requires_admin(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "viewer@aura.local", "role": "viewer"},
    )
    monkeypatch.setattr(facade, "_api_json", lambda **_: {"agents": []})

    with pytest.raises(RuntimeError, match="admin role required"):
        facade.shutdown(_shutdown_args(scope="all"))


def test_shutdown_scope_session_requires_identity_or_task_id(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    monkeypatch.setattr(facade, "_api_json", lambda **_: {"agents": []})

    with pytest.raises(RuntimeError, match="missing explicit identity filters"):
        facade.shutdown(_shutdown_args(scope="session"))


def test_shutdown_scope_session_kills_only_target_session(tmp_path, monkeypatch):
    facade, shell_calls = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    deleted: list[str] = []

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = token, params, json_body
        if method == "GET" and path == "/api/v1/agents/running":
            return {
                "agents": [
                    {"agent_id": "agent-1", "task_id": "task-1"},
                    {"agent_id": "agent-2", "task_id": "task-2"},
                ]
            }
        if method == "GET" and path == "/api/v1/tasks/task-1":
            return {
                "id": "task-1",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                    "workflow_kind": "track_b_discovery",
                },
            }
        if method == "DELETE" and path == "/api/v1/agents/agent-1":
            deleted.append(path)
            return {"status": "killed"}
        raise AssertionError(f"Unexpected {method} {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)
    result = facade.shutdown(_shutdown_args(scope="session", task_id="task-1"))
    assert result["classification"] == "PASS"
    assert result["scope"] == "session"
    assert result["killed_agents"] == ["agent-1"]
    assert result["services_stopped"] is False
    assert shell_calls == []
    assert deleted == ["/api/v1/agents/agent-1"]


def test_shutdown_scope_track_requires_track_and_ownership(tmp_path, monkeypatch):
    facade, _ = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    monkeypatch.setattr(facade, "_api_json", lambda **_: {"agents": []})

    with pytest.raises(RuntimeError, match="missing explicit identity filters"):
        facade.shutdown(_shutdown_args(scope="track", track="B"))


def test_shutdown_scope_track_kills_only_matching_ownership(tmp_path, monkeypatch):
    facade, shell_calls = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    deleted: list[str] = []

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = token, params, json_body
        if method == "GET" and path == "/api/v1/agents/running":
            return {
                "agents": [
                    {"agent_id": "agent-1", "task_id": "task-1"},
                    {"agent_id": "agent-2", "task_id": "task-2"},
                    {"agent_id": "agent-3", "task_id": "task-3"},
                ]
            }
        if method == "GET" and path == "/api/v1/tasks/task-1":
            return {
                "id": "task-1",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                    "workflow_kind": "track_b_discovery",
                    "platform": "sc7280",
                },
            }
        if method == "GET" and path == "/api/v1/tasks/task-2":
            return {
                "id": "task-2",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                    "workflow_kind": "another_kind",
                    "platform": "sc7280",
                },
            }
        if method == "GET" and path == "/api/v1/tasks/task-3":
            return {
                "id": "task-3",
                "input_data": {
                    "track": "A",
                    "ownership": "track_a",
                    "workflow_kind": "runtime_capture",
                },
            }
        if method == "DELETE" and path.startswith("/api/v1/agents/"):
            deleted.append(path.split("/")[-1])
            return {"status": "killed"}
        raise AssertionError(f"Unexpected {method} {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)
    result = facade.shutdown(
        _shutdown_args(
            scope="track",
            track="B",
            ownership="track_b",
            session_kind="track_b_discovery",
            platform="sc7280",
        )
    )
    assert result["classification"] == "PASS"
    assert result["killed_agents"] == ["agent-1"]
    assert result["services_stopped"] is False
    assert shell_calls == []
    assert deleted == ["agent-1"]


def test_shutdown_scope_track_fail_closed_on_identity_validation_error(tmp_path, monkeypatch):
    facade, shell_calls = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    deleted: list[str] = []

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = token, params, json_body
        if method == "GET" and path == "/api/v1/agents/running":
            return {"agents": [{"agent_id": "agent-1", "task_id": "task-invalid"}]}
        if method == "GET" and path == "/api/v1/tasks/task-invalid":
            # workflow_kind missing -> identity validation must fail closed
            return {
                "id": "task-invalid",
                "input_data": {
                    "track": "B",
                    "ownership": "track_b",
                },
            }
        if method == "DELETE" and path.startswith("/api/v1/agents/"):
            deleted.append(path.split("/")[-1])
            return {"status": "killed"}
        raise AssertionError(f"Unexpected {method} {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)

    with pytest.raises(RuntimeError, match="shutdown --scope track task_id=task-invalid"):
        facade.shutdown(
            _shutdown_args(
                scope="track",
                track="B",
                ownership="track_b",
            )
        )

    # Fail-closed means no termination side effects occurred.
    assert deleted == []
    assert shell_calls == []


def test_shutdown_scope_all_stops_services_for_admin(tmp_path, monkeypatch):
    facade, shell_calls = _make_facade(tmp_path, monkeypatch)
    monkeypatch.setattr(
        facade,
        "_login",
        lambda: {"token": "tok", "email": "admin@aura.local", "role": "admin"},
    )
    deleted: list[str] = []

    def _api_json(*, method, path, token, params=None, json_body=None):
        _ = token, params, json_body
        if method == "GET" and path == "/api/v1/agents/running":
            return {"agents": [{"agent_id": "agent-1", "task_id": "task-1"}]}
        if method == "DELETE" and path == "/api/v1/agents/agent-1":
            deleted.append("agent-1")
            return {"status": "killed"}
        raise AssertionError(f"Unexpected {method} {path}")

    monkeypatch.setattr(facade, "_api_json", _api_json)
    result = facade.shutdown(_shutdown_args(scope="all"))
    assert result["classification"] == "PASS"
    assert result["scope"] == "all"
    assert result["services_stopped"] is True
    assert result["killed_agents"] == ["agent-1"]
    assert deleted == ["agent-1"]
    assert shell_calls
