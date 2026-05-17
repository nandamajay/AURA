"""LLM gateway endpoint regression tests."""

from fastapi.testclient import TestClient

from llm_gateway.budget import TokenBudgetManager
from llm_gateway.cache import ResponseCache
from llm_gateway.main import app
from llm_gateway import main as llm_main


def _reset_gateway_state() -> None:
    """Reset mutable globals to keep tests deterministic."""
    llm_main.cache = ResponseCache(maxsize=100)
    llm_main.budget = TokenBudgetManager(daily_limit=1_000_000)
    llm_main.Config.LLM_PROVIDER = "qgenie"
    llm_main.Config.LLM_MOCK_MODE = True


def test_health_and_root_endpoints():
    _reset_gateway_state()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "llm-gateway"
    assert payload["mock_mode"] is True

    root = client.get("/")
    assert root.status_code == 200
    assert "/v1/completions" in root.json()["endpoints"]


def test_completions_mock_mode_and_cache_hit():
    _reset_gateway_state()
    client = TestClient(app)

    req = {
        "agent_type": "learning",
        "task_id": "task-cache-1",
        "model": "gpt-4o-2024-08-06",
        "messages": [{"role": "user", "content": "find upstream patterns"}],
        "max_tokens": 120,
        "seed": 42,
    }

    first = client.post("/v1/completions", json=req)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["mock_mode"] is True
    assert first_payload["provider"] == "qgenie"
    assert first_payload["cached"] is False
    assert "MOCK_RESPONSE" in first_payload["content"]

    second = client.post("/v1/completions", json=req)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["cached"] is True
    assert second_payload["content"] == first_payload["content"]

    budget = client.get("/budget")
    assert budget.status_code == 200
    budget_payload = budget.json()
    assert budget_payload["used_today"] > 0
    assert budget_payload["remaining"] < budget_payload["daily_limit"]


def test_budget_enforcement_returns_429():
    _reset_gateway_state()
    llm_main.budget = TokenBudgetManager(daily_limit=1)
    client = TestClient(app)

    req = {
        "agent_type": "learning",
        "task_id": "task-budget-1",
        "messages": [{"role": "user", "content": "x" * 100}],
        "max_tokens": 100,
    }

    response = client.post("/v1/completions", json=req)
    assert response.status_code == 429
    assert response.json()["detail"] == "Daily token budget exceeded"


def test_completions_rejects_non_object_json_body():
    _reset_gateway_state()
    client = TestClient(app)

    response = client.post("/v1/completions", json=[])
    assert response.status_code == 422


def test_completions_rejects_malformed_json():
    _reset_gateway_state()
    client = TestClient(app)

    response = client.post(
        "/v1/completions",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
