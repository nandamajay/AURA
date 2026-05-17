# AURA Platform — Unified Architecture Blueprint
## Artifacts 1-5: Architecture, Infrastructure, Orchestration, Agent Lifecycle, Events
### Version: 1.0 | Stage: Architecture Stabilization | Date: 2026-05-15

---

## ARTIFACT 1: Unified Architecture Blueprint

### 1.1 Consolidation Summary

After analyzing all 11 specification files across 10 refinement passes, the architecture has been consolidated from 11 overlapping modules into **8 stable subsystems** with clearly defined boundaries, contracts, and dependencies.

| Subsystem | Code | Source Files | Status |
|-----------|------|-------------|--------|
| Orchestrator | S1 | #3, #10 | Consolidated — single brain |
| Agent Runtime | S2 | #3, #4, #10 | Merged — 14 agents, all CLI |
| Knowledge System | S3 | #3, #4, #6, #13 | Merged — 4-tier learning |
| Simulation Engine | S4 | #5, #9 | Merged — hybrid fidelity |
| Dashboard | S5 | #3, #5, #7, #8, #9 | Merged — 12 pages |
| Governance | S6 | #7, #8, #11, #13 | Merged — 3 pillars |
| LLM Gateway | S7 | #3, #4, #5, #12 | New subsystem — extracted |
| Validation Engine | S8 | #3, #5 | Extracted — kernel toolchain |

### 1.2 Critical Architecture Decisions

| # | Decision | Rationale | Risk if Wrong |
|---|----------|-----------|---------------|
| AD-01 | 8 subsystems (not 11+) | Eliminates overlap, clear ownership | Refactoring later |
| AD-02 | All agents are CLI executables | File #10 mandate, true isolation | Higher spawn overhead |
| AD-03 | SQLite (not PostgreSQL) | Local-first, zero-config, 20-user scale | Migration needed at scale |
| AD-04 | Hybrid simulation (state machine + QEMU) | Balances speed and fidelity | Neither mode gets full investment |
| AD-05 | Multi-provider LLM gateway | Cost optimization, capability matching | Complex fallback logic |
| AD-06 | 5-phase governance (not 8-auth from day 1) | 5-minute setup, incremental | May need to accelerate |
| AD-07 | Plugin abstraction from day 1 | Validated architecture without over-engineering | Wrong abstraction |
| AD-08 | Read-only kernel source access | Licensing safety, no storage duplication | Performance from network mounts |
| AD-09 | Subprocess isolation (not containers per agent) | Fast startup, low overhead, sufficient | Less isolation than containers |
| AD-10 | Event-driven dashboard (not polling) | Real-time, efficient, scalable | WebSocket complexity |

### 1.3 Dependency Graph

```
                    S7 (LLM Gateway)
                    ↑ (every agent needs inference)
    S5 (Dashboard) ← S1 (Orchestrator) → S8 (Validation)
                        ↓
            ┌───────────┼───────────┐
            ↓           ↓           ↓
        S2 (Agents)  S3 (Knowledge) S4 (Simulation)
                        ↓
                    S6 (Governance)
```

**Critical Path:** S7 → S1 → (S2, S3, S4) → S5

**Hard Dependencies:**
- S1 cannot function without S7 (LLM inference)
- S1 cannot function without S2 (agent spawning)
- S1 cannot function without S3 (knowledge reads/writes)
- S5 cannot function without S1 (orchestrator state)
- S2 cannot function without S8 (validation toolchain)

**Soft Dependencies:**
- S4 → S8 (simulation may validate)
- S5 → S4, S6 (dashboard displays)
- S3 → S6 (audit queries)

### 1.4 Data Flow Architecture

**Three channels:**

1. **Command Channel** (S1 ↔ S2): Subprocess stdin/stdout with JSON envelopes
   - Task dispatch: `{task_id, agent_type, rules_path, input_data}`
   - Progress reports: `{task_id, status, progress_pct, partial_results}`
   - Final results: `{task_id, status, results, evidence, confidence}`

2. **Event Channel** (S1 → S5): WebSocket + SSE
   - Agent state changes: `AGENT_SPAWNED`, `AGENT_COMPLETED`, `AGENT_FAILED`
   - Orchestration events: `TASK_QUEUED`, `TASK_STARTED`, `TASK_COMPLETED`
   - Simulation events: `SIM_STARTED`, `SIM_PROGRESS`, `SIM_COMPLETED`
   - Governance events: `APPROVAL_REQUIRED`, `ESCALATION_TRIGGERED`

3. **Persistence Channel** (S1 ↔ S3, S6): SQLite + filesystem
   - Structured data: SQLite tables (rules, evidence, audit)
   - Markdown memory: Agent skill files + findings
   - Kernel sources: Read-only mounted filesystem

---

## ARTIFACT 2: Infrastructure Topology

### 2.1 Docker Compose Specification

```yaml
version: "3.8"

services:
  aura-core:
    build: ./services/core
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./rules:/rules:ro
      - ${KERNEL_SOURCES_PATH:-/dev/null}:/kernel-sources:ro
    environment:
      - SQLITE_PATH=/data/aura.db
      - RULES_PATH=/rules
      - LLM_GATEWAY_URL=http://llm-gateway:8000
      - WS_SERVER_URL=http://ws-server:8001
      - MAX_CONCURRENT_AGENTS=50
      - AGENT_TIMEOUT_SECONDS=300
    depends_on:
      - llm-gateway
      - ws-server
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
      interval: 30s
      timeout: 10s
      retries: 3

  aura-dashboard:
    build: ./dashboard
    ports:
      - "3000:80"
    environment:
      - API_URL=http://aura-core:8000
      - WS_URL=ws://ws-server:8001
    depends_on:
      - aura-core
      - ws-server

  llm-gateway:
    build: ./services/llm-gateway
    ports:
      - "8002:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OLLAMA_URL=${OLLAMA_URL:-}
      - DEFAULT_PROVIDER=openai
      - TOKEN_BUDGET_DAILY=1000000
      - RESPONSE_CACHE_SIZE=10000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  ws-server:
    build: ./services/ws-server
    ports:
      - "8001:8000"
    environment:
      - CORE_API_URL=http://aura-core:8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  qemu-runner:
    build: ./services/qemu-runner
    profiles: ["qemu"]
    environment:
      - DEV_COMPUTE_HOST=${DEV_COMPUTE_HOST}
      - DEV_COMPUTE_SSH_KEY=${DEV_COMPUTE_SSH_KEY}
    volumes:
      - ./data/qemu-results:/results
    depends_on:
      - aura-core
```

### 2.2 Network Architecture

| Service | Port | Exposure | Purpose |
|---------|------|----------|---------|
| aura-dashboard | 3000 | External | User-facing React SPA |
| aura-core | 8000 | External | REST API for dashboard |
| ws-server | 8001 | Internal only | WebSocket/SSE events |
| llm-gateway | 8002 | Internal only | LLM proxy + cache |
| qemu-runner | N/A | Internal only | SSH to dev compute |

### 2.3 Storage Architecture

| Storage | Path | Type | Purpose |
|---------|------|------|---------|
| SQLite DB | `./data/aura.db` | Host volume | Knowledge + audit |
| WAL files | `./data/aura.db-wal` | Host volume | Write-ahead log |
| Agent rules | `./rules/*.md` | Host volume (ro) | Agent skill definitions |
| Agent output | `./data/agents/{task_id}/` | Host volume | Agent findings, logs |
| Kernel sources | `${KERNEL_SOURCES_PATH}` | Host volume (ro) | Upstream + downstream trees |
| Backups | `./data/backups/` | Host volume | Daily SQLite backups |
| Temp workspace | `./data/tmp/` | Host volume | Compilation, git worktrees |

### 2.4 Resource Budget

| Component | CPU | RAM | Disk | Notes |
|-----------|-----|-----|------|-------|
| aura-core | 2 cores | 4 GB | 10 GB | Orchestrator + API |
| aura-dashboard | 1 core | 1 GB | 1 GB | Static files + nginx |
| llm-gateway | 2 cores | 4 GB | 2 GB | Proxy + in-memory cache |
| ws-server | 1 core | 2 GB | 500 MB | WebSocket connections |
| agent pool (max 50) | 10 cores | 20 GB | 30 GB | Shared pool |
| validation | 2 cores | 4 GB | 20 GB | Kernel compilation |
| SQLite + temp | 0.5 core | 2 GB | 36 GB | Cache + worktrees |
| **Total** | **~18 cores** | **~37 GB** | **~100 GB** | **With headroom** |

**Minimum viable hardware:** 8 CPU cores, 16 GB RAM, 50 GB disk
**Recommended hardware:** 16 CPU cores, 32 GB RAM, 100 GB disk

---

## ARTIFACT 3: Runtime Orchestration Architecture

### 3.1 Orchestrator Components

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR (S1)                       │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   REST API   │  │   Scheduler  │  │  Circuit     │     │
│  │   (FastAPI)  │  │   Engine     │  │  Breaker     │     │
│  └──────┬───────┘  └──────┬───────┘  │  Manager     │     │
│         │                  │          └──────┬───────┘     │
│         │           ┌──────┴──────┐          │             │
│         │           │ Task Queue  │◄─────────┘             │
│         │           │ (Priority)  │                        │
│         │           └──────┬──────┘                        │
│         │                  │                                │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────────────┐       │
│  │  Dependency │  │   Agent     │  │   Watchdog   │       │
│  │    Graph    │  │   Spawner   │  │   Manager    │       │
│  │   Engine    │  │  (subprocess)│  │  (timers)    │       │
│  └─────────────┘  └─────────────┘  └──────────────┘       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Event Dispatcher                        │   │
│  │  (WebSocket + SSE to dashboard)                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Task Lifecycle State Machine

```
CREATED → QUEUED → ASSIGNED → SPAWNING → RUNNING → COMPLETED
                                            ↓
                                      ┌─────┴─────┐
                                      ↓           ↓
                                   FAILED      TIMEOUT
                                      │           │
                                      └─────┬─────┘
                                            ↓
                                      RETRY_PENDING
                                            │
                              (max 3 retries) → back to QUEUED
                              (max retries exceeded) → TERMINAL_FAILED
```

### 3.3 Scheduling Algorithm

**Priority Queue with 3 Tiers:**

```python
class TaskPriority(IntEnum):
    P0_CRITICAL = 0    # Governance actions, circuit breaker triggers
    P1_NORMAL = 1      # Migration tasks, validation, review
    P2_BACKGROUND = 2  # Learning, pattern extraction

class Scheduler:
    def next_task(self) -> Optional[Task]:
        # P0: FIFO — critical tasks first
        if self.p0_queue:
            return self.p0_queue.popleft()
        # P1: Round-robin across agent types (fairness)
        for agent_type in self.round_robin_order:
            task = self.p1_queues[agent_type].popleft()
            if task:
                return task
        # P2: Best-effort (only if resources available)
        if self.current_load < self.max_load * 0.5:
            return self.p2_queue.popleft()
        return None

    @property
    def max_concurrent_agents(self) -> int:
        return 50  # Configurable
```

### 3.4 Circuit Breaker Specification

| Parameter | Value |
|-----------|-------|
| Failure threshold | 3 failures in 60 seconds |
| Cooldown period | 30 seconds |
| Probe requests (half-open) | 1 |
| Success to close | 1 consecutive success |
| Failure to re-open | 1 failure |
| Affected scope | Per agent type (not global) |

**States:**
- `CLOSED`: Normal operation. Track failure count.
- `OPEN`: Reject all requests immediately. Return cached error.
- `HALF_OPEN`: After cooldown. Allow 1 probe request.

### 3.5 Watchdog Specification

| Parameter | Value |
|-----------|-------|
| Heartbeat interval | 30 seconds (agent sends) |
| Missed threshold | 3 heartbeats = 90 seconds |
| Graceful shutdown (SIGTERM) | 10 second timeout |
| Force kill (SIGKILL) | After SIGTERM timeout |
| Max retries per task | 3 |
| Retry backoff | 5s, 15s, 45s (exponential) |

---

## ARTIFACT 4: Agent Lifecycle Specification

### 4.1 14 Agent Taxonomy

| # | Agent | Type | Category | Always Running |
|---|-------|------|----------|---------------|
| 1 | Chief Orchestrator | Singleton | Core | Yes |
| 2 | Learning Agent | Pool | Core | No |
| 3 | Driver Dependency Agent | Pool | Core | No |
| 4 | DTS/Bindings Agent | Pool | Core | No |
| 5 | Upstream Philosophy Agent | Pool | Core | No |
| 6 | Refactor Agent | Pool | Core | No |
| 7 | Validation Agent | Pool | Core | No |
| 8 | Regression Intelligence Agent | Pool | Core | No |
| 9 | Knowledge Base Agent | Singleton | Core | Yes |
| 10 | Dashboard Agent | Singleton | Core | Yes |
| 11 | Maintainer Intelligence Reviewer | Pool | Extended | No |
| 12 | Feature Pruning Agent | Pool | Extended | No |
| 13 | Legal Compliance Agent | Pool | Extended | No |
| 14 | Human Question Agent | Pool | Extended | No |

### 4.2 CLI Execution Contract

```
Entry:     python -m agents.{agent_name} [command] [options]
           --task-id <uuid>        # Required: task identifier
           --rules <path>          # Required: skill markdown file
           --input <path>          # Optional: JSON input file
           --output-dir <path>     # Required: output directory
           --llm-gateway <url>     # Required: LLM gateway endpoint
           --max-tokens <int>      # Optional: token limit
           --timeout <seconds>     # Optional: execution timeout

Input:     JSON via stdin (if --input not provided)
Output:    JSON to stdout (results)
           Markdown files to --output-dir (findings, evidence)
           Structured JSON logs to stderr

Exit Codes:
  0: Success — results valid, evidence complete
  1: Validation failed — output rejected by internal checks
  2: Unrecoverable error — no retry (e.g., bad input)
  3: Timeout — watchdog killed, retryable
  4: Resource exhaustion — OOM, disk full, retryable
  5: LLM gateway unavailable — retry with fallback
```

### 4.3 Agent Process Pool

```python
class AgentPool:
    """Pre-warmed process pool for fast agent startup."""

    def __init__(self):
        self.warm_pool: deque[subprocess.Popen] = deque(maxlen=20)
        self.active: dict[str, subprocess.Popen] = {}
        self.max_total = 50  # Hard limit

    async def acquire(self, agent_type: str) -> subprocess.Popen:
        # Try warm pool first
        if self.warm_pool:
            proc = self.warm_pool.popleft()
            return proc
        # Spawn new if under limit
        if len(self.active) < self.max_total:
            return await self._spawn(agent_type)
        # Wait for slot
        raise ResourceExhausted("Max concurrent agents reached")

    def release(self, proc: subprocess.Popen) -> None:
        proc.stdin.close()
        if proc.poll() is None:  # Still alive
            self.warm_pool.append(proc)
        else:
            proc.wait(timeout=5)
```

### 4.4 Agent Rules Format

Each agent loads a markdown rule file at startup:

```markdown
# Agent: Learning Agent

## Purpose
Autonomously learn upstreaming patterns from Qualcomm Audio drivers.

## Capabilities
- Identify upstreamed drivers
- Compare downstream vs upstream implementations
- Extract migration patterns

## Constraints
- Never modify source files
- Always produce evidence with citations
- Confidence threshold: 0.7

## Output Format
```json
{
  "patterns": [...],
  "evidence": [...],
  "confidence": 0.0-1.0
}
```

## Failure Modes
- Incomplete upstream references → reduce confidence
- Ambiguous patterns → request human clarification
```

---

## ARTIFACT 5: Event-Driven Communication Architecture

### 5.1 Event Taxonomy

| Category | Events | Frequency | Payload Size |
|----------|--------|-----------|--------------|
| Agent Lifecycle | `AGENT_SPAWNED`, `AGENT_HEARTBEAT`, `AGENT_COMPLETED`, `AGENT_FAILED`, `AGENT_TIMEOUT` | High (~100/min) | ~500B |
| Task Orchestration | `TASK_CREATED`, `TASK_QUEUED`, `TASK_STARTED`, `TASK_PROGRESS`, `TASK_COMPLETED` | High (~50/min) | ~1KB |
| Simulation | `SIM_STARTED`, `SIM_PROGRESS`, `SIM_COMPLETED`, `SIM_FAILED` | Medium (~10/min) | ~2KB |
| Governance | `APPROVAL_REQUIRED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED`, `ESCALATION_TRIGGERED` | Low (~5/min) | ~2KB |
| LLM Usage | `LLM_REQUEST`, `LLM_RESPONSE`, `LLM_ERROR`, `LLM_CACHE_HIT` | High (~200/min) | ~500B |

### 5.2 Event Schema

```json
{
  "event_id": "uuid",
  "event_type": "AGENT_COMPLETED",
  "timestamp": "2026-05-15T10:30:00Z",
  "source": {
    "subsystem": "S2",
    "agent_type": "learning",
    "agent_id": "uuid",
    "task_id": "uuid"
  },
  "payload": {
    "status": "success",
    "confidence": 0.92,
    "patterns_found": 15,
    "output_path": "/data/agents/{task_id}/findings.md"
  },
  "trace_id": "uuid",
  "correlation_id": "uuid"
}
```

### 5.3 Communication Patterns

**Pattern 1: Orchestrator → Dashboard (Broadcast)**
```
Orchestrator → WebSocket → Dashboard (all connected clients)
Purpose: Agent state changes, task progress
Delivery: At-most-once (dropped events acceptable)
```

**Pattern 2: Orchestrator → Agent (Point-to-point)**
```
Orchestrator → subprocess stdin → Agent
Agent → subprocess stdout → Orchestrator
Purpose: Task dispatch, results collection
Delivery: At-least-once (orchestrator tracks ACK)
```

**Pattern 3: Agent → Knowledge (Write-only)**
```
Agent → SQLite INSERT → Knowledge Base
Purpose: Evidence persistence, rule storage
Delivery: Best-effort (async batch writes)
```

**Pattern 4: Dashboard → Orchestrator (Request/Response)**
```
Dashboard → HTTP POST → Orchestrator → HTTP Response
Purpose: User actions (approve, reject, configure)
Delivery: Exactly-once (idempotent operations)
```

### 5.4 WebSocket Architecture

```
Dashboard (React)        ws-server (FastAPI)        Orchestrator
      │                          │                        │
      │── WS CONNECT ───────────►│                        │
      │◄── CONNECTION ACK ──────│                        │
      │                          │◄── SUBSCRIBE event_bus │
      │                          │                        │
      │◄── AGENT_COMPLETED ─────│◄── PUBLISH event ──────│
      │◄── TASK_PROGRESS ───────│                        │
      │◄── SIM_STARTED ─────────│                        │
      │                          │                        │
      │── WS DISCONNECT ───────►│                        │
```

**Connection Management:**
- Max connections: 100 (sufficient for 20 users)
- Heartbeat: 30s ping/pong
- Reconnection: Exponential backoff (1s, 2s, 4s, max 30s)
- Message buffer: Last 100 events per client (replay on reconnect)

---

## ARCHITECTURAL RISKS IDENTIFIED

| Risk ID | Risk | Severity | Mitigation | Owner |
|---------|------|----------|------------|-------|
| R-01 | SQLite write bottleneck at scale | Medium | WAL mode, batch writes, upgrade path | S3 |
| R-02 | LLM API rate limiting under load | Medium | Token bucket, local fallback, queue | S7 |
| R-03 | Agent process pool exhaustion | Medium | Pre-warmed pool, backpressure, limits | S1 |
| R-04 | WebSocket fan-out at 20 users | Low | Async server, event batching | S5 |
| R-05 | QEMU simulation blocks resources | Medium | Toggle off by default, remote execution | S4 |
| R-06 | Kernel compilation OOM | Medium | Single-job queue, resource limits | S8 |
| R-07 | Governance circular dependency | Low | Read-only governance queries | S1/S6 |
| R-08 | LLM cost overrun | Medium | Per-agent budgets, daily caps, alerts | S7 |
| R-09 | Plugin abstraction wrong | Medium | Interface review, audio validates first | S1 |
| R-10 | Subprocess spawn overhead | Low | Pre-warmed pool, process reuse | S1 |
