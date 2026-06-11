"""Routing and parser tests for aura facade CLI."""

from __future__ import annotations

import json

from aura_agents import aura_facade


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
