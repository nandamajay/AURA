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
    ws_main._event_ingest_sequence = 0
    ws_main._seen_event_ids.clear()
    ws_main._retry_attempt_state.clear()
    ws_main._stream_sequence_state.clear()
    ws_main._buffer_evictions_total = 0
    ws_main._buffer_evictions_by_domain.clear()
    ws_main._sse_drop_total = 0
    ws_main._sse_drop_by_domain.clear()
    ws_main._domain_ingest_count.clear()
    ws_main._domain_ws_delivery_count.clear()
    ws_main._domain_sse_delivery_count.clear()
    ws_main._channel_broadcast_count.clear()


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


def test_broadcast_deduplicates_event_id_and_keeps_single_buffer_entry():
    _reset_ws_state()
    client = TestClient(app)

    event = {
        "event_id": "dup-1",
        "event_type": "task.progress",
        "payload": {"task_id": "task-dup-1"},
        "timestamp": "2026-05-16T00:00:00Z",
    }

    first = client.post("/broadcast", json={"channel": "task.orchestration", "event": event})
    second = client.post("/broadcast", json={"channel": "task.orchestration", "event": event})
    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["dropped_duplicate"] is False
    assert second.json()["dropped_duplicate"] is True
    assert second.json()["ordering"]["duplicate_event"] is True
    assert len(ws_main._event_buffer) == 1


def test_broadcast_normalizes_retry_attempts_to_monotonic_order():
    _reset_ws_state()
    client = TestClient(app)

    attempts_seen: list[int] = []
    originals: list[int | None] = []
    for attempt in [2, 1, 3]:
        event = {
            "event_id": f"retry-evt-{attempt}",
            "event_type": "runtime.discovery.retry",
            "payload": {"marker": "m1", "kind": "retry", "op": "R1", "attempt": attempt},
            "timestamp": "2026-05-16T00:00:00Z",
        }
        response = client.post("/broadcast", json={"channel": "system", "event": event})
        assert response.status_code == 200
        body = response.json()
        assert body["dropped_duplicate"] is False

    for buffered in ws_main._event_buffer:
        payload = buffered.get("payload", {})
        if payload.get("kind") == "retry":
            attempts_seen.append(int(payload["attempt"]))
            original = payload.get("attempt_original")
            originals.append(int(original) if original is not None else None)

    assert attempts_seen == [1, 2, 3]
    # First two retries were normalized; third was already the expected attempt.
    assert originals == [2, 1, None]


def test_retry_normalization_is_scoped_by_plugin_domain():
    _reset_ws_state()
    client = TestClient(app)

    for domain in ["driver", "media"]:
        for attempt in [2, 1, 3]:
            event = {
                "event_id": f"retry-{domain}-{attempt}",
                "event_type": "runtime.discovery.retry",
                "payload": {
                    "run_id": "r1",
                    "plugin_domain": domain,
                    "kind": "retry",
                    "op": "shared-op",
                    "attempt": attempt,
                },
                "timestamp": "2026-05-16T00:00:00Z",
            }
            response = client.post("/broadcast", json={"channel": "system", "event": event})
            assert response.status_code == 200

    attempts_by_domain: dict[str, list[int]] = {"driver": [], "media": []}
    for buffered in ws_main._event_buffer:
        payload = buffered.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") != "retry":
            continue
        domain = str(payload.get("plugin_domain") or "")
        if domain in attempts_by_domain:
            attempts_by_domain[domain].append(int(payload["attempt"]))

    assert attempts_by_domain["driver"] == [1, 2, 3]
    assert attempts_by_domain["media"] == [1, 2, 3]


def test_broadcast_routes_to_domain_scoped_channels():
    _reset_ws_state()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws_driver:
        _ = ws_driver.receive_json()
        ws_driver.send_json({"action": "subscribe", "channels": ["system:driver"]})
        _ = ws_driver.receive_json()

        driver_event = {
            "event_type": "runtime.discovery.driver",
            "payload": {"plugin_domain": "driver", "marker": "m1"},
            "timestamp": "2026-05-16T00:00:00Z",
        }
        media_event = {
            "event_type": "runtime.discovery.media",
            "payload": {"plugin_domain": "media", "marker": "m2"},
            "timestamp": "2026-05-16T00:00:00Z",
        }

        driver_resp = client.post("/broadcast", json={"channel": "system", "event": driver_event})
        media_resp = client.post("/broadcast", json={"channel": "system", "event": media_event})
        assert driver_resp.status_code == 200
        assert media_resp.status_code == 200
        assert driver_resp.json()["recipients"] == 1
        assert media_resp.json()["recipients"] == 0

        received = ws_driver.receive_json()
        assert received["payload"]["plugin_domain"] == "driver"
        assert received["_routing"]["channels"] == ["system", "system:driver"]


def test_sse_live_fanout_matches_scoped_channels():
    _reset_ws_state()
    client = TestClient(app)

    queue_driver: asyncio.Queue[dict] = asyncio.Queue()
    queue_media: asyncio.Queue[dict] = asyncio.Queue()
    ws_main._sse_clients["driver"] = {"queue": queue_driver, "channels": {"system:driver"}}
    ws_main._sse_clients["media"] = {"queue": queue_media, "channels": {"system:media"}}

    driver_event = {
        "event_type": "runtime.discovery.driver",
        "payload": {"plugin_domain": "driver", "marker": "m1"},
        "timestamp": "2026-05-16T00:00:00Z",
    }
    media_event = {
        "event_type": "runtime.discovery.media",
        "payload": {"plugin_domain": "media", "marker": "m2"},
        "timestamp": "2026-05-16T00:00:00Z",
    }

    assert client.post("/broadcast", json={"channel": "system", "event": driver_event}).status_code == 200
    assert client.post("/broadcast", json={"channel": "system", "event": media_event}).status_code == 200

    assert queue_driver.qsize() == 1
    assert queue_media.qsize() == 1
    assert queue_driver.get_nowait()["payload"]["plugin_domain"] == "driver"
    assert queue_media.get_nowait()["payload"]["plugin_domain"] == "media"


def test_coexistence_metrics_endpoint_exposes_pressure_counters():
    _reset_ws_state()
    client = TestClient(app)

    event = {
        "event_type": "runtime.discovery.driver",
        "payload": {"plugin_domain": "driver", "marker": "m1", "kind": "retry", "op": "r", "attempt": 2},
        "timestamp": "2026-05-16T00:00:00Z",
    }
    assert client.post("/broadcast", json={"channel": "system", "event": event}).status_code == 200

    metrics = client.get("/metrics/coexistence")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["event_buffer_size"] >= 1
    assert "domain_ingest_count" in body
    assert body["domain_ingest_count"].get("driver", 0) >= 1
    assert "retry_scope_tracked" in body


def test_broadcast_marks_sequence_violation_for_out_of_order_stream():
    _reset_ws_state()
    client = TestClient(app)

    event_1 = {
        "event_id": "ooo-1",
        "event_type": "runtime.discovery.order",
        "payload": {"marker": "stream-a", "kind": "out_of_order", "seq": 5},
        "timestamp": "2026-05-16T00:00:00Z",
    }
    event_2 = {
        "event_id": "ooo-2",
        "event_type": "runtime.discovery.order",
        "payload": {"marker": "stream-a", "kind": "out_of_order", "seq": 3},
        "timestamp": "2026-05-16T00:00:00Z",
    }

    first = client.post("/broadcast", json={"channel": "system", "event": event_1})
    second = client.post("/broadcast", json={"channel": "system", "event": event_2})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["ordering"]["sequence_violation"] is True
    assert second.json()["ordering"]["expected_seq"] == 6
    assert second.json()["ordering"]["received_seq"] == 3
