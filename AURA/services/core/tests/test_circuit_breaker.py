"""Circuit breaker FSM regression tests."""

import pytest

from core.services.circuit_breaker import CircuitBreakerConfig, CircuitBreakerManager, CircuitState


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold_failures_within_window():
    now = {"value": 0.0}
    manager = CircuitBreakerManager(
        config=CircuitBreakerConfig(
            failure_threshold=3,
            window_seconds=60.0,
            cooldown_seconds=30.0,
        ),
        now_fn=lambda: now["value"],
    )

    allowed, reason = await manager.allow_request("learning")
    assert allowed is True
    assert reason == "closed"

    await manager.record_failure("learning", reason="f1")
    now["value"] = 10.0
    await manager.record_failure("learning", reason="f2")
    now["value"] = 20.0
    await manager.record_failure("learning", reason="f3")

    state = manager.get_state("learning")
    assert state["state"] == CircuitState.OPEN.value
    assert state["failure_count_window"] == 3

    allowed, reason = await manager.allow_request("learning")
    assert allowed is False
    assert reason.startswith("circuit_open:")


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_probe_success_transitions_to_closed():
    now = {"value": 0.0}
    manager = CircuitBreakerManager(
        config=CircuitBreakerConfig(
            failure_threshold=3,
            window_seconds=60.0,
            cooldown_seconds=30.0,
        ),
        now_fn=lambda: now["value"],
    )

    await manager.record_failure("learning", reason="f1")
    await manager.record_failure("learning", reason="f2")
    await manager.record_failure("learning", reason="f3")
    assert manager.get_state("learning")["state"] == CircuitState.OPEN.value

    now["value"] = 31.0
    allowed, reason = await manager.allow_request("learning")
    assert allowed is True
    assert reason == "half_open_probe_allowed"
    assert manager.get_state("learning")["state"] == CircuitState.HALF_OPEN.value

    second_allowed, second_reason = await manager.allow_request("learning")
    assert second_allowed is False
    assert second_reason == "half_open_probe_in_flight"

    await manager.record_success("learning")
    state = manager.get_state("learning")
    assert state["state"] == CircuitState.CLOSED.value
    assert state["failure_count_window"] == 0
    assert state["half_open_probe_in_flight"] is False


@pytest.mark.asyncio
async def test_circuit_breaker_prunes_failures_outside_60_second_window():
    now = {"value": 0.0}
    manager = CircuitBreakerManager(
        config=CircuitBreakerConfig(
            failure_threshold=3,
            window_seconds=60.0,
            cooldown_seconds=30.0,
        ),
        now_fn=lambda: now["value"],
    )

    await manager.record_failure("learning", reason="f1")
    now["value"] = 61.0
    await manager.record_failure("learning", reason="f2")
    now["value"] = 62.0
    await manager.record_failure("learning", reason="f3")

    state = manager.get_state("learning")
    assert state["state"] == CircuitState.CLOSED.value
    assert state["failure_count_window"] == 2

    now["value"] = 63.0
    await manager.record_failure("learning", reason="f4")
    state = manager.get_state("learning")
    assert state["state"] == CircuitState.OPEN.value
    assert state["failure_count_window"] == 3
