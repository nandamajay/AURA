"""WebSocket server endpoint regression tests."""

import asyncio

from fastapi.testclient import TestClient

from ws_server.main import app
from ws_server import main as ws_main


def _reset_ws_state() -> None:
    ws_main.manager._connections.clear()
    ws_main.manager._subscriptions.clear()
    ws_main._event_buffer.clear()
    ws_main._sse_clients.clear()


def test_health_endpoint_reports_connections():
    _reset_ws_state()
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "ws-server"
    assert payload["connections"] == 0


def test_websocket_subscribe_and_broadcast_delivery():
    _reset_ws_state()
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["action"] == "connected"

        websocket.send_json({"action": "subscribe", "channels": ["task.orchestration"]})
        subscribed = websocket.receive_json()
        assert subscribed["action"] == "subscribed"
        assert "task.orchestration" in subscribed["channels"]

        event = {
            "event_type": "task.created",
            "payload": {"task_id": "task-123"},
            "timestamp": "2026-05-16T00:00:00Z",
        }
        broadcast = client.post("/broadcast", json={"channel": "task.orchestration", "event": event})
        assert broadcast.status_code == 200
        assert broadcast.json()["broadcast"] is True
        assert broadcast.json()["recipients"] == 1

        received = websocket.receive_json()
        assert received["event_type"] == "task.created"
        assert received["payload"]["task_id"] == "task-123"


def test_websocket_ping_pong_and_unknown_action():
    _reset_ws_state()
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # connected event

        websocket.send_json({"action": "ping"})
        assert websocket.receive_json() == {"action": "pong"}

        websocket.send_json({"action": "unknown"})
        error = websocket.receive_json()
        assert error["action"] == "error"
        assert "Unknown action" in error["message"]


def test_broadcast_buffers_channel_metadata_for_sse_replay():
    _reset_ws_state()
    client = TestClient(app)

    event_task = {
        "event_type": "task.created",
        "payload": {"task_id": "task-replay-1"},
        "timestamp": "2026-05-16T00:00:00Z",
    }
    assert client.post("/broadcast", json={"channel": "task.orchestration", "event": event_task}).status_code == 200
    assert len(ws_main._event_buffer) == 1
    buffered = ws_main._event_buffer[0]
    assert buffered["channel"] == "task.orchestration"
    assert buffered["channels"] == ["task.orchestration"]
    assert buffered["event_type"] == "task.created"
    assert buffered["payload"]["task_id"] == "task-replay-1"


def test_broadcast_queues_live_events_for_matching_sse_subscribers():
    _reset_ws_state()
    client = TestClient(app)

    queue_task: asyncio.Queue[dict] = asyncio.Queue()
    queue_all: asyncio.Queue[dict] = asyncio.Queue()
    queue_agent: asyncio.Queue[dict] = asyncio.Queue()

    ws_main._sse_clients["task-only"] = {"queue": queue_task, "channels": {"task.orchestration"}}
    ws_main._sse_clients["all-channels"] = {"queue": queue_all, "channels": set()}
    ws_main._sse_clients["agent-only"] = {"queue": queue_agent, "channels": {"agent.lifecycle"}}

    event = {
        "event_type": "task.created",
        "payload": {"task_id": "task-live-1"},
        "timestamp": "2026-05-16T00:00:00Z",
    }
    broadcast = client.post("/broadcast", json={"channel": "task.orchestration", "event": event})
    assert broadcast.status_code == 200

    assert queue_task.qsize() == 1
    assert queue_all.qsize() == 1
    assert queue_agent.qsize() == 0

    queued_event = queue_task.get_nowait()
    assert queued_event["channel"] == "task.orchestration"
    assert queued_event["event_type"] == "task.created"


def test_broadcast_rejects_missing_channel():
    _reset_ws_state()
    client = TestClient(app)

    response = client.post("/broadcast", json={"event": {"event_type": "task.created"}})
    assert response.status_code == 422


def test_broadcast_rejects_non_object_json_body():
    _reset_ws_state()
    client = TestClient(app)

    response = client.post("/broadcast", json=[])
    assert response.status_code == 422


def test_broadcast_rejects_malformed_json():
    _reset_ws_state()
    client = TestClient(app)

    response = client.post(
        "/broadcast",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
