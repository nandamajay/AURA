"""Agent runtime timeout resolution regression tests."""

from core.services.agent_runtime import _resolve_spawn_timeout


def test_resolve_spawn_timeout_prefers_explicit_request():
    timeout = _resolve_spawn_timeout(
        requested_timeout=120,
        agent_type="learning",
        runtime_default_timeout=300,
        agent_default_timeouts={"learning": 600},
    )
    assert timeout == 120


def test_resolve_spawn_timeout_uses_agent_default_when_not_overridden():
    timeout = _resolve_spawn_timeout(
        requested_timeout=None,
        agent_type="learning",
        runtime_default_timeout=300,
        agent_default_timeouts={"learning": 600},
    )
    assert timeout == 600


def test_resolve_spawn_timeout_falls_back_to_runtime_default():
    timeout = _resolve_spawn_timeout(
        requested_timeout=None,
        agent_type="validation",
        runtime_default_timeout=300,
        agent_default_timeouts={"learning": 600},
    )
    assert timeout == 300
