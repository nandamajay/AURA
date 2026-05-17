"""Tests for aura-sdk models."""

import pytest
from aura_sdk.models.event import EventEnvelope, EventType, EventSource
from aura_sdk.models.agent import AgentType, AgentStatus, AgentSpawnRequest
from aura_sdk.models.task import TaskCreate, TaskPriority, TaskStatus
from aura_sdk.models.governance import User, Role, Permission
from aura_sdk.models.health import ComponentHealth, HealthResponse, HealthStatus


class TestEventModels:
    def test_event_envelope_creation(self):
        event = EventEnvelope(
            event_type=EventType.AGENT_SPAWNED,
            source=EventSource(subsystem="S1", service="core"),
            payload={"agent_type": "learning"},
        )
        assert event.event_type == EventType.AGENT_SPAWNED
        assert event.source.subsystem == "S1"
        assert event.payload["agent_type"] == "learning"

    def test_event_json_roundtrip(self):
        event = EventEnvelope(
            event_type=EventType.TASK_COMPLETED,
            source=EventSource(subsystem="S1", task_id="test-123"),
            payload={"result": "success"},
        )
        json_str = event.to_json()
        restored = EventEnvelope.from_json(json_str)
        assert restored.event_type == EventType.TASK_COMPLETED
        assert restored.payload["result"] == "success"


class TestAgentModels:
    def test_agent_types_defined(self):
        types = list(AgentType)
        assert len(types) >= 10
        assert AgentType.LEARNING in types
        assert AgentType.REFACTOR in types

    def test_spawn_request_defaults(self):
        req = AgentSpawnRequest(agent_type=AgentType.LEARNING)
        assert req.seed == 42
        assert req.timeout_seconds == 300


class TaskModels:
    def test_task_priority_values(self):
        assert TaskPriority.CRITICAL == "P0"
        assert TaskPriority.NORMAL == "P1"
        assert TaskPriority.BACKGROUND == "P2"


class TestGovernanceModels:
    def test_role_permissions(self):
        admin = User(email="admin@aura.local", role=Role.ADMIN)
        assert admin.has_permission(Permission.USER_MANAGE)

        viewer = User(email="viewer@aura.local", role=Role.VIEWER)
        assert viewer.has_permission(Permission.DASHBOARD_READ)
        assert not viewer.has_permission(Permission.PATCH_APPROVE)


class TestHealthModels:
    def test_health_response(self):
        health = HealthResponse(
            service="test",
            status=HealthStatus.HEALTHY,
            components=[
                ComponentHealth(name="db", status=HealthStatus.HEALTHY, latency_ms=5),
            ],
        )
        assert health.is_healthy is True
        assert health.is_ready is True
