"""Tests for public `aura` entrypoint wrapper."""

from __future__ import annotations

from aura_agents import aura_cli


def test_cli_entrypoint_delegates_to_facade(monkeypatch):
    seen: dict[str, object] = {}

    def _fake_facade_main(argv=None):
        seen["argv"] = argv
        return 17

    monkeypatch.setattr(aura_cli, "facade_main", _fake_facade_main)
    rc = aura_cli.main(["status"])
    assert rc == 17
    assert seen["argv"] == ["status"]
