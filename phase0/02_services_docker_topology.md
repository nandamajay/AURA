# AURA Phase 0 — Service Contracts & Docker Topology
## Implementation-Grade Blueprint | Artifact P0-2
### Status: READY FOR SCAFFOLDING

---

## SERVICE-BY-SERVICE BREAKDOWN

### SRV-1: aura-core (Orchestrator)

| Property | Specification |
|----------|---------------|
| **Responsibility** | Central brain. Task scheduling, agent lifecycle, circuit breakers, dependency graphs, governance queries |
| **Language** | Python 3.12 |
| **Framework** | FastAPI 0.110 + uvicorn |
| **Port** | 8000 (external) |
| **Package** | Depends on `aura-sdk[db,log]` |
| **Type** | Singleton — one instance |

#### Startup Requirements (order matters)
1. Validate environment (SQLITE_PATH, LLM_GATEWAY_URL, WS_SERVER_URL)
2. Connect to SQLite (WAL mode, verify schema version)
3. Connect to llm-gateway (health check)
4. Connect to ws-server (health check)
5. Initialize plugin registry (scan ./plugins/)
6. Start event bus dispatcher
7. Start scheduler loop
8. Start watchdog loop
9. Mark ready

#### API Surface
```python
# Routers mounted at /api/v1/

# agents.py
@router.get("/agents")                          # List agent types + counts
@router.get("/agents/running")                  # List running agent instances
@router.post("/agents/{type}/spawn")            # Spawn agent (body: task_input)
@router.delete("/agents/{id}")                  # Kill agent

# tasks.py
@router.get("/tasks")                           # Paginated, filterable
@router.get("/tasks/{id}")                      # Task details + progress
@router.post("/tasks")                          # Create task
@router.patch("/tasks/{id}/cancel")             # Cancel task
@router.get("/queue")                           # Queue statistics

# patches.py
@router.get("/patches")                         # List patches
@router.get("/patches/{id}")                    # Patch details
@router.get("/patches/{id}/diff")               # Get diff
@router.get("/patches/{id}/evidence")           # Evidence links
@router.post("/patches/{id}/submit-approval")    # Submit for approval

# knowledge.py
@router.get("/rules")                           # Search rules
@router.get("/rules/{id}")                      # Rule details
@router.get("/search")                          # FTS5 search
@router.post("/export")                         # Export (json/csv)

# governance.py
@router.get("/approvals")                       # Pending approvals
@router.post("/approvals/{id}")                 # Approve/reject/escalate
@router.get("/audit")                           # Audit log

# simulation.py
@router.post("/simulate")                       # Start simulation
@router.get("/simulate/{id}")                   # Status
@router.get("/scenarios")                       # Available scenarios

# auth.py
@router.post("/auth/login")                     # Email/password
@router.post("/auth/logout")                    # Invalidate session
@router.get("/auth/me")                         # Current user

# health.py
@router.get("/health/live")                     # Liveness
@router.get("/health/ready")                    # Readiness
@router.get("/metrics")                         # Prometheus format
```

#### Dependencies
- `llm-gateway:8000` — HTTP (spawned agents call LLM)
- `ws-server:8000` — HTTP (publish events for broadcast)
- `SQLite` — File on host volume (`./data/aura.db`)
- `./rules/` — Read-only mount
- `./plugins/` — Read-only mount

#### Failure Modes
| Mode | Detection | Recovery |
|------|-----------|----------|
| SQLite locked | Timeout on write | Retry with exponential backoff |
| LLM gateway unreachable | HTTP error | Queue tasks, retry every 60s |
| WS server unreachable | HTTP error | Buffer events, retry every 30s |
| Agent spawn failure | subprocess exception | Circuit breaker opens |
| Schema version mismatch | Startup check | Run migrations |

#### Observability Hooks
```python
# Startup
event_bus.publish(EventEnvelope(
    event_type=EventType.SERVICE_STARTED,
    source=EventSource(subsystem="S1", service="core"),
    payload={"version": "0.1.0", "components": ["scheduler", "agent_pool", ...]}
))

# Task lifecycle
event_bus.publish(EventEnvelope(
    event_type=EventType.TASK_STARTED,
    source=EventSource(subsystem="S1", service="core", task_id=task.id),
    payload={"agent_type": task.agent_type, "priority": task.priority}
))

# Circuit breaker
event_bus.publish(EventEnvelope(
    event_type=EventType.CIRCUIT_BREAKER_STATE,
    source=EventSource(subsystem="S1", service="core"),
    payload={"agent_type": "refactor", "state": "OPEN", "reason": "3 failures in 60s"}
))
```

#### Scaling Assumptions
- Single instance (MVP)
- Handles 50 concurrent agents
- 200 tasks/hour throughput
- 20 concurrent dashboard users

---

### SRV-2: llm-gateway

| Property | Specification |
|----------|---------------|
| **Responsibility** | Proxy LLM requests to OpenAI. Token budget enforcement. Response caching. Cost attribution. |
| **Language** | Python 3.12 |
| **Framework** | FastAPI + httpx (async HTTP client) |
| **Port** | 8000 (internal only) |
| **Package** | Depends on `aura-sdk[log]` |
| **Type** | Singleton |

#### Startup Requirements
1. Validate OPENAI_API_KEY
2. Test OpenAI connection (lightweight ping)
3. Initialize response cache (LRU, 10K entries)
4. Reset daily token counters
5. Mark ready

#### API Surface
```python
@router.post("/v1/completions")              # Proxy to LLM
@router.get("/health")                       # Liveness
@router.get("/budget")                       # Current token usage
@router.post("/cache/clear")                 # Clear response cache
```

**Request** (body):
```json
{
    "agent_type": "learning",
    "task_id": "uuid",
    "model": "gpt-4o",
    "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
    "temperature": 0.1,
    "max_tokens": 4000,
    "seed": 42
}
```

**Response** (body):
```json
{
    "content": "The driver uses...",
    "usage": {"prompt_tokens": 1500, "completion_tokens": 800, "total_tokens": 2300, "cost_usd": 0.0345},
    "cached": false,
    "provider": "openai",
    "model": "gpt-4o-2024-08-06"
}
```

#### Dependencies
- `api.openai.com` — HTTPS (external)
- None internally (no other services call it except via core's agents)

#### Failure Modes
| Mode | Detection | Recovery |
|------|-----------|----------|
| OpenAI rate limit | HTTP 429 | Retry after Retry-After header |
| OpenAI timeout | HTTP timeout | Retry up to 3x with backoff |
| OpenAI down | HTTP 5xx | Return 503, client retries |
| Token budget exceeded | Budget check | Return 429, daily budget exhausted |
| Cache corruption | Validation | Clear cache, continue |

#### Observability Hooks
```python
event_bus.publish(EventEnvelope(
    event_type=EventType.LLM_REQUEST,
    source=EventSource(subsystem="S7", service="llm-gateway"),
    payload={"agent_type": req.agent_type, "tokens_estimated": ..., "model": req.model}
))
```

#### Scaling Assumptions
- Single instance (MVP)
- 200 req/min throughput
- 10K cache entries
- $100/day token budget default

---

### SRV-3: ws-server

| Property | Specification |
|----------|---------------|
| **Responsibility** | WebSocket connections from dashboard. SSE fallback. Event broadcasting. Connection management. |
| **Language** | Python 3.12 |
| **Framework** | FastAPI WebSocket + SSE |
| **Port** | 8000 (internal only) |
| **Package** | Depends on `aura-sdk[log]` |
| **Type** | Singleton |

#### Startup Requirements
1. Initialize connection manager (max 100 connections)
2. Initialize event hub (subscribe to all channels)
3. Mark ready

#### API Surface
```python
@router.websocket("/ws")              # WebSocket endpoint
@router.get("/events")                # SSE endpoint (fallback)
@router.get("/health")                # Liveness
```

**WebSocket Protocol:**
```json
// Client -> Server
{"action": "subscribe", "channels": ["agent.lifecycle", "task.orchestration"]}
{"action": "unsubscribe", "channels": ["simulation"]}
{"action": "ping"}  // Heartbeat

// Server -> Client
{"event_type": "agent.spawned", "payload": {...}, "timestamp": "..."}
{"action": "pong"}  // Heartbeat response
```

#### Dependencies
- Receives events from `aura-core` via internal HTTP POST `/broadcast`
- No external dependencies

#### Failure Modes
| Mode | Detection | Recovery |
|------|-----------|----------|
| Connection limit | Connection count | Reject with 429 |
| Client disconnect | WebSocket close | Clean up, no alert |
| Message backlog | Queue depth > 100 | Drop oldest, log warning |

#### Observability Hooks
- Connection count gauge
- Messages sent counter
- Active subscriptions gauge

#### Scaling Assumptions
- 100 max WebSocket connections
- Async — handles 20 concurrent users easily
- Events batched (100ms window) to reduce message count

---

### SRV-4: aura-dashboard

| Property | Specification |
|----------|---------------|
| **Responsibility** | React SPA. 12 pages. WebSocket client. Charts. Diff viewer. Chat panel. |
| **Language** | TypeScript |
| **Framework** | React 18 + Vite |
| **Port** | 80 (nginx serves static build) |
| **Build** | `npm run build` produces `dist/` |
| **Type** | Stateless — any number of replicas |

#### Startup Requirements (client-side)
1. Load config from `window.__AURA_CONFIG__` (injected by nginx)
2. Check auth (redirect to login if no JWT)
3. Establish WebSocket connection
4. Subscribe to default channels
5. Load initial data (GET /api/v1/agents, GET /api/v1/tasks)

#### Dependencies
- `aura-core:8000` — REST API
- `ws-server:8000` — WebSocket + SSE

#### Failure Modes
| Mode | Detection | Recovery |
|------|-----------|----------|
| API unreachable | HTTP error | Retry with backoff, show offline banner |
| WS disconnect | onclose event | Exponential reconnect (1s, 2s, 4s, max 30s) |
| Slow loading | Timeout | Show skeleton UI, load incrementally |

---

## DOCKER COMPOSE TOPOLOGY

### docker-compose.yml (Production)

```yaml
version: "3.8"

networks:
  aura-internal:
    driver: bridge
    internal: false  # llm-gateway needs external

volumes:
  aura-data:
    driver: local
  aura-logs:
    driver: local

services:
  # ── SQLite initialization ──
  # No separate container. SQLite is a file on host volume.
  # Core service runs migrations on startup.

  # ── Service 1: LLM Gateway (starts first) ──
  llm-gateway:
    build:
      context: .
      dockerfile: services/llm-gateway/Dockerfile
    container_name: aura-llm-gateway
    networks:
      - aura-internal
    ports:
      - "127.0.0.1:8002:8000"  # Localhost only — internal service
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY:?Error: OPENAI_API_KEY not set}
      - TOKEN_BUDGET_DAILY=${TOKEN_BUDGET_DAILY:-1000000}
      - CACHE_SIZE=${CACHE_SIZE:-10000}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"

  # ── Service 2: WebSocket Server (starts second) ──
  ws-server:
    build:
      context: .
      dockerfile: services/ws-server/Dockerfile
    container_name: aura-ws-server
    networks:
      - aura-internal
    ports:
      - "127.0.0.1:8001:8000"  # Localhost only
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - MAX_CONNECTIONS=100
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 5s
    restart: unless-stopped
    depends_on:
      llm-gateway:
        condition: service_healthy  # Wait for LLM gateway
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"

  # ── Service 3: Core Orchestrator (starts third) ──
  aura-core:
    build:
      context: .
      dockerfile: services/core/Dockerfile
    container_name: aura-core
    networks:
      - aura-internal
    ports:
      - "8000:8000"  # External — dashboard calls this
    environment:
      - SQLITE_PATH=/data/aura.db
      - RULES_PATH=/rules
      - PLUGINS_PATH=/plugins
      - LLM_GATEWAY_URL=http://llm-gateway:8000
      - WS_SERVER_URL=http://ws-server:8000
      - MAX_CONCURRENT_AGENTS=${MAX_CONCURRENT_AGENTS:-50}
      - AGENT_TIMEOUT_SECONDS=${AGENT_TIMEOUT_SECONDS:-300}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - JWT_SECRET=${JWT_SECRET:?Error: JWT_SECRET not set}
      - ADMIN_EMAIL=${ADMIN_EMAIL:-admin@aura.local}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}
    volumes:
      - aura-data:/data
      - ./rules:/rules:ro
      - ./plugins:/plugins:ro
      - ${KERNEL_SOURCES_PATH:-./data/empty}:/kernel-sources:ro
      - aura-logs:/data/logs
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped
    depends_on:
      llm-gateway:
        condition: service_healthy
      ws-server:
        condition: service_started
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "10"

  # ── Service 4: Dashboard (starts last) ──
  aura-dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    container_name: aura-dashboard
    networks:
      - aura-internal
    ports:
      - "3000:80"  # External — user-facing
    environment:
      - API_URL=http://aura-core:8000
      - WS_URL=ws://ws-server:8000
    depends_on:
      aura-core:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped
```

### docker-compose.override.yml (Development)

```yaml
# Development overrides — loaded automatically with docker compose up
version: "3.8"

services:
  aura-core:
    volumes:
      # Hot reload: mount source code
      - ./services/core/src:/app/src:ro
      - ./workspace/aura-sdk/src:/workspace/aura-sdk/src:ro
      - ./governance/src:/app/governance:ro
      - ./knowledge/src:/app/knowledge:ro
      - ./simulation/src:/app/simulation:ro
      - ./validation/src:/app/validation:ro
    environment:
      - LOG_LEVEL=DEBUG
      - UVICORN_RELOAD=true
    command: uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload

  llm-gateway:
    volumes:
      - ./services/llm-gateway/src:/app/src:ro
      - ./workspace/aura-sdk/src:/workspace/aura-sdk/src:ro
    environment:
      - LOG_LEVEL=DEBUG
    command: uvicorn llm_gateway.main:app --host 0.0.0.0 --port 8000 --reload

  ws-server:
    volumes:
      - ./services/ws-server/src:/app/src:ro
      - ./workspace/aura-sdk/src:/workspace/aura-sdk/src:ro
    environment:
      - LOG_LEVEL=DEBUG
    command: uvicorn ws_server.main:app --host 0.0.0.0 --port 8000 --reload

  aura-dashboard:
    volumes:
      - ./dashboard/src:/app/src:ro
      - ./dashboard/public:/app/public:ro
    environment:
      - NODE_ENV=development
      - VITE_API_URL=http://localhost:8000
      - VITE_WS_URL=ws://localhost:8001
```

### Dockerfile Templates

```dockerfile
# services/core/Dockerfile
FROM python:3.12-slim AS base

WORKDIR /workspace
COPY workspace/aura-sdk /workspace/aura-sdk
RUN pip install --no-cache-dir /workspace/aura-sdk[db,log]

WORKDIR /app
COPY services/core/pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY services/core/src ./src
COPY governance/src ./governance
COPY knowledge/src ./knowledge
COPY simulation/src ./simulation
COPY validation/src ./validation

EXPOSE 8000
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Multi-stage for smaller image ──
FROM base AS production
RUN pip uninstall -y pytest pytest-asyncio && rm -rf /app/tests
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

```dockerfile
# dashboard/Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

## SERVICE STARTUP ORDER

```
Phase 0: Docker network created (aura-internal)
    │
Phase 1: llm-gateway starts
    │  → Validates OPENAI_API_KEY
    │  → Tests OpenAI connection
    │  → Healthcheck: /health
    │
Phase 2: ws-server starts
    │  → Waits for llm-gateway (healthy)
    │  → Initializes connection manager
    │  → Healthcheck: /health
    │
Phase 3: aura-core starts
    │  → Waits for llm-gateway (healthy)
    │  → Waits for ws-server (started)
    │  → Runs SQLite migrations
    │  → Scans plugins
    │  → Starts scheduler + watchdog
    │  → Healthcheck: /health/ready
    │
Phase 4: aura-dashboard starts
    │  → Waits for aura-core (healthy)
    │  → Waits for ws-server (started)
    │  → Serves static files
    │
Phase 5: Bootstrap wizard (on first startup)
    │  → Detects empty users table
    │  → Creates admin account from env vars
    │  → Logs: "Bootstrap complete. Login with ADMIN_EMAIL/ADMIN_PASSWORD"
```

**Startup time budget:**
- llm-gateway: 5s
- ws-server: 3s
- aura-core: 15s (migrations)
- aura-dashboard: 1s
- Total: ~25s from `make up` to ready

---

## NETWORK ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────┐
│                     Docker Bridge: aura-internal              │
│                                                               │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │ aura-dashboard│◄────►│  aura-core   │                     │
│  │   Port 80     │ HTTP │  Port 8000   │                     │
│  │   (external)  │      │ (external)   │                     │
│  └──────────────┘      └──────┬───────┘                     │
│                               │                               │
│                               │ HTTP                          │
│                               │                               │
│                      ┌────────┴────────┐                     │
│                      │                 │                     │
│              ┌───────▼──────┐  ┌──────▼──────┐             │
│              │ llm-gateway  │  │  ws-server   │             │
│              │  Port 8000   │  │  Port 8000   │             │
│              │  (internal)  │  │  (internal)  │             │
│              └──────┬───────┘  └─────────────┘             │
│                     │                                         │
│                     │ HTTPS                                   │
│                     │                                         │
│              ┌──────▼───────┐                                │
│              │ api.openai.com │  EXTERNAL                     │
│              └──────────────┘                                │
│                                                               │
│  Host mounts:                                                 │
│    ./data → aura-data volume → /data (SQLite + logs)         │
│    ./rules → bind mount → /rules (read-only)                 │
│    ./plugins → bind mount → /plugins (read-only)             │
│    KERNEL_SOURCES_PATH → bind mount → /kernel-sources (ro)   │
└──────────────────────────────────────────────────────────────┘
```
