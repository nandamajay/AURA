# Live Agent Observability Report

Generated: 2026-05-24T14:14:57.478703+00:00

## Endpoint Health
- `GET http://localhost:8001/health` -> 200
- `GET http://localhost:8001/metrics/coexistence` -> 200
- `GET /api/v1/agents/running` -> 200
- `GET /api/v1/agents/watchdog` -> 200
- `GET /health/runtime-overview` -> 200

## Stabilization Changes
- WebSocket client now includes active auth token context.
- WebSocket closure/error states are explicitly surfaced.
- Polling surfaces remain evidence-backed and correlated with runtime overview metrics.

## Current Runtime State
- Active agents: 0
- Watchdog tracked agents: 0 / 50
- Queue pressure: all queues idle in current snapshot
- Coexistence drops: sse_drop_total=0 buffer_evictions_total=0

## Risks / Blockers
- Observability is healthy but workload-idle; no active long-running agent traces in this snapshot.
