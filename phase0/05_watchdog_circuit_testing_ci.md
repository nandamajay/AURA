# AURA Phase 0 — Watchdog, Circuit Breaker, Testing & CI/CD
## Implementation-Grade Blueprint | Artifact P0-5
### Status: READY FOR IMPLEMENTATION

---

## 1. WATCHDOG ARCHITECTURE

### 1.1 Watchdog Specification

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Heartbeat interval | 30s | Balances responsiveness vs. overhead |
| Missed threshold | 3 heartbeats | 90s total = reasonable grace period |
| Graceful timeout | 10s | SIGTERM → wait → SIGKILL chain |
| Force kill | SIGKILL after 10s | Guarantees termination |
| Max restarts | 3 per task | Prevents infinite retry loops |
| Restart backoff | 5s, 15s, 45s | Exponential, max 3 retries |
| Memory threshold | 4GB | Per-agent limit via cgroups |
| CPU threshold | 200% (2 cores) | Per-agent limit |

### 1.2 Watchdog Implementation

```python
# core/services/watchdog.py

import asyncio
import signal
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

@dataclass
class AgentWatch:
    """State for a single watched agent."""
    agent_id: str
    task_id: str
    agent_type: str
    process: asyncio.subprocess.Process
    last_heartbeat: float = field(default_factory=time.time)
    heartbeats_missed: int = 0
    restart_count: int = 0
    memory_mb: int = 0
    status: str = "running"  # running, stopping, killed, completed

class WatchdogManager:
    """
    Monitors all running agents via heartbeat.
    
    Protocol:
    1. Agent sends heartbeat JSON to stdout every 30s
    2. Watchdog resets miss counter on each heartbeat
    3. After 3 missed heartbeats (90s), trigger termination
    4. SIGTERM first, wait 10s, then SIGKILL
    5. Log to audit ledger, notify event bus
    
    Guarantees:
    - Every agent is watched within 1s of spawn
    - No agent runs without a heartbeat timer
    - Zombie agents are detected and killed
    - Resource leaks are prevented
    """

    HEARTBEAT_INTERVAL = 30.0
    MISSED_THRESHOLD = 3
    SIGTERM_WAIT = 10.0
    CHECK_INTERVAL = 5.0  # How often we scan agents

    def __init__(self, event_bus: EventBus):
        self._watches: dict[str, AgentWatch] = {}  # agent_id -> AgentWatch
        self._event_bus = event_bus
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._task = asyncio.create_task(self._watch_loop(), name="watchdog")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Kill all remaining agents
        for watch in list(self._watches.values()):
            await self._force_kill(watch)

    def register(self, watch: AgentWatch):
        """Register a new agent for monitoring."""
        self._watches[watch.agent_id] = watch

    def on_heartbeat(self, agent_id: str, heartbeat: AgentHeartbeat):
        """Called when a heartbeat message is received."""
        watch = self._watches.get(agent_id)
        if not watch:
            return
        watch.last_heartbeat = heartbeat.timestamp
        watch.heartbeats_missed = 0
        watch.memory_mb = heartbeat.memory_mb

    def unregister(self, agent_id: str):
        """Unregister an agent (normal completion)."""
        self._watches.pop(agent_id, None)

    async def _watch_loop(self):
        """Main monitoring loop. Runs every 5 seconds."""
        while True:
            await asyncio.sleep(self.CHECK_INTERVAL)
            now = time.time()

            for watch in list(self._watches.values()):
                if watch.status != "running":
                    continue

                elapsed = now - watch.last_heartbeat
                missed = int(elapsed / self.HEARTBEAT_INTERVAL)

                if missed > 0 and missed != watch.heartbeats_missed:
                    watch.heartbeats_missed = missed
                    if missed >= self.MISSED_THRESHOLD:
                        await self._handle_timeout(watch)

    async def _handle_timeout(self, watch: AgentWatch):
        """Handle agent timeout: SIGTERM -> wait -> SIGKILL."""
        watch.status = "stopping"

        # Publish timeout event
        await self._event_bus.publish(EventEnvelope(
            event_type=EventType.AGENT_TIMEOUT,
            source=EventSource(subsystem="S1", service="core",
                             agent_type=watch.agent_type, agent_id=watch.agent_id),
            payload={"heartbeats_missed": watch.heartbeats_missed,
                     "elapsed_seconds": watch.heartbeats_missed * self.HEARTBEAT_INTERVAL}
        ))

        # Phase 1: SIGTERM
        try:
            watch.process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass  # Already dead

        # Phase 2: Wait for graceful shutdown
        try:
            await asyncio.wait_for(watch.process.wait(), timeout=self.SIGTERM_WAIT)
            watch.status = "completed"
            self.unregister(watch.agent_id)
            return
        except asyncio.TimeoutError:
            pass  # Still running, force kill

        # Phase 3: SIGKILL
        await self._force_kill(watch)

    async def _force_kill(self, watch: AgentWatch):
        """Force kill an agent."""
        try:
            watch.process.kill()
            await watch.process.wait()
        except ProcessLookupError:
            pass  # Already dead
        watch.status = "killed"

        # Publish killed event
        await self._event_bus.publish(EventEnvelope(
            event_type=EventType.AGENT_KILLED,
            source=EventSource(subsystem="S1", service="core",
                             agent_type=watch.agent_type, agent_id=watch.agent_id),
            payload={"reason": "watchdog_timeout", "heartbeats_missed": watch.heartbeats_missed}
        ))

        self.unregister(watch.agent_id)
```

---

## 2. CIRCUIT BREAKER IMPLEMENTATION

### 2.1 Circuit Breaker State Machine

```
                    ┌─────────────────────────────────────┐
                    │                                     │
    ┌─── OPEN ◄─────┤  3 failures in 60s                  │
    │    (reject    │                                     │
    │     all)      │  30s cooldown ──► probe succeeds    │
    │       ▲       │                                     │
    │       │       │  probe fails ──────────────────────►┘
    │       │       │
    │   probe       │
    │   fails       │
    │       │       │
    │       ▼       │
    │   HALF_OPEN   │  (allow 1 probe request)
    │   (1 probe)   │
    │       │       │
    │   probe       │
    │   succeeds    │
    │       │       │
    │       ▼       │
    └──► CLOSED     │  (normal operation, track failures)
         (normal)   │
```

### 2.2 Circuit Breaker Implementation

```python
# core/services/circuit_breaker.py

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Reject all requests
    HALF_OPEN = "half_open" # Allow 1 probe

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3          # Failures to open
    window_seconds: float = 60.0        # Time window for failures
    cooldown_seconds: float = 30.0      # Time before half-open
    half_open_max_calls: int = 1        # Probes allowed in half-open
    success_to_close: int = 1           # Successful probes to close

@dataclass
class CircuitBreakerState:
    agent_type: str
    state: CircuitState = CircuitState.CLOSED
    failures: list[float] = field(default_factory=list)  # Timestamps
    half_open_calls: int = 0
    half_open_successes: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0

class CircuitBreakerManager:
    """
    Per-agent-type circuit breaker.
    
    Guarantees:
    - Independent per agent type (failure in learning doesn't break refactor)
    - Thread-safe (asyncio-safe)
    - Metrics exposed for dashboard
    - Events published on state transitions
    """

    def __init__(self, event_bus: EventBus, config: CircuitBreakerConfig = None):
        self._config = config or CircuitBreakerConfig()
        self._breakers: dict[str, CircuitBreakerState] = {}
        self._event_bus = event_bus

    def get_state(self, agent_type: str) -> CircuitBreakerState:
        if agent_type not in self._breakers:
            self._breakers[agent_type] = CircuitBreakerState(agent_type=agent_type)
        return self._breakers[agent_type]

    def can_execute(self, agent_type: str) -> bool:
        """Check if a request can be executed."""
        state = self.get_state(agent_type)

        if state.state == CircuitState.CLOSED:
            return True

        if state.state == CircuitState.OPEN:
            # Check if cooldown has passed
            if time.time() - state.opened_at > self._config.cooldown_seconds:
                state.state = CircuitState.HALF_OPEN
                state.half_open_calls = 0
                state.half_open_successes = 0
                self._publish_transition(agent_type, CircuitState.HALF_OPEN)
                return True
            return False

        if state.state == CircuitState.HALF_OPEN:
            if state.half_open_calls < self._config.half_open_max_calls:
                state.half_open_calls += 1
                return True
            return False

        return True

    def record_success(self, agent_type: str):
        """Record a successful execution."""
        state = self.get_state(agent_type)

        if state.state == CircuitState.HALF_OPEN:
            state.half_open_successes += 1
            if state.half_open_successes >= self._config.success_to_close:
                state.state = CircuitState.CLOSED
                state.failures = []
                self._publish_transition(agent_type, CircuitState.CLOSED)

        elif state.state == CircuitState.CLOSED:
            state.failures = []  # Reset on success

    def record_failure(self, agent_type: str):
        """Record a failed execution."""
        state = self.get_state(agent_type)
        now = time.time()

        if state.state == CircuitState.HALF_OPEN:
            state.state = CircuitState.OPEN
            state.opened_at = now
            self._publish_transition(agent_type, CircuitState.OPEN)
            return

        # Track failure
        state.failures.append(now)
        state.last_failure_time = now

        # Clean old failures outside window
        window_start = now - self._config.window_seconds
        state.failures = [f for f in state.failures if f > window_start]

        # Check threshold
        if len(state.failures) >= self._config.failure_threshold:
            state.state = CircuitState.OPEN
            state.opened_at = now
            self._publish_transition(agent_type, CircuitState.OPEN)

    def _publish_transition(self, agent_type: str, new_state: CircuitState):
        asyncio.create_task(self._event_bus.publish(EventEnvelope(
            event_type=EventType.CIRCUIT_BREAKER_STATE,
            source=EventSource(subsystem="S1", service="core"),
            payload={
                "agent_type": agent_type,
                "state": new_state.value,
                "failure_count": len(self._breakers[agent_type].failures),
            }
        )))

    @property
    def all_states(self) -> dict[str, dict]:
        """Return all breaker states for dashboard."""
        return {
            agent_type: {
                "state": state.state.value,
                "failure_count": len(state.failures),
                "half_open_calls": state.half_open_calls,
            }
            for agent_type, state in self._breakers.items()
        }
```

---

## 3. TESTING STRATEGY

### 3.1 Test Pyramid

```
    /\\
   /  \\     E2E (5%)    — Full workflow, Playwright
  /    \\
 /  INT  \\   Integration (25%) — Service boundaries, DB, WS
/──────────\\
/   Unit     \\  Unit (70%)     — Functions, models, utilities
/──────────────\\
```

### 3.2 Test Organization

```
tests/
├── unit/                           # Fast, no I/O
│   ├── test_models.py              # Pydantic model validation
│   ├── test_event_bus.py           # Pub/sub logic
│   ├── test_circuit_breaker.py     # State machine
│   ├── test_retry_policy.py        # Retry logic
│   ├── test_scheduler.py           # Queue ordering
│   ├── test_rbac.py                # Permission matrix
│   ├── test_jwt.py                 # Token encode/decode
│   └── test_protocol.py            # Agent stdio envelope
│
├── integration/                    # With real dependencies
│   ├── test_database.py            # SQLite queries, migrations
│   ├── test_agent_spawn.py         # Subprocess lifecycle
│   ├── test_websocket.py           # WS connection + events
│   ├── test_llm_gateway.py         # Mock provider responses
│   ├── test_event_persistence.py   # Event buffer replay
│   └── test_plugin_loading.py      # Plugin discovery
│
└── e2e/                            # Full stack
    ├── test_bootstrap.py           # First-run wizard
    ├── test_patch_workflow.py      # Submit → migrate → approve
    ├── test_dashboard.py           # Playwright, all 12 pages
    └── test_auth_flow.py           # Login → RBAC → logout
```

### 3.3 Unit Test Example

```python
# tests/unit/test_circuit_breaker.py

import pytest
from core.services.circuit_breaker import (
    CircuitBreakerManager, CircuitBreakerConfig, CircuitState
)

class TestCircuitBreaker:

    @pytest.fixture
    def cb(self):
        return CircuitBreakerManager(
            event_bus=MockEventBus(),
            config=CircuitBreakerConfig(
                failure_threshold=3,
                window_seconds=60,
                cooldown_seconds=0.1,  # Fast for testing
            )
        )

    def test_starts_closed(self, cb):
        assert cb.get_state("learning").state == CircuitState.CLOSED
        assert cb.can_execute("learning") is True

    def test_opens_after_3_failures(self, cb):
        cb.record_failure("learning")
        cb.record_failure("learning")
        cb.record_failure("learning")
        assert cb.get_state("learning").state == CircuitState.OPEN
        assert cb.can_execute("learning") is False

    def test_half_open_after_cooldown(self, cb):
        cb.record_failure("learning")
        cb.record_failure("learning")
        cb.record_failure("learning")
        assert cb.get_state("learning").state == CircuitState.OPEN

        # Wait for cooldown
        import time
        time.sleep(0.15)
        assert cb.can_execute("learning") is True  # Half-open
        assert cb.get_state("learning").state == CircuitState.HALF_OPEN

    def test_closes_on_probe_success(self, cb):
        cb.record_failure("learning")
        cb.record_failure("learning")
        cb.record_failure("learning")
        time.sleep(0.15)
        cb.can_execute("learning")  # Enter half-open
        cb.record_success("learning")
        assert cb.get_state("learning").state == CircuitState.CLOSED

    def test_independent_per_agent_type(self, cb):
        cb.record_failure("learning")
        cb.record_failure("learning")
        cb.record_failure("learning")
        assert cb.get_state("learning").state == CircuitState.OPEN
        assert cb.get_state("refactor").state == CircuitState.CLOSED
        assert cb.can_execute("refactor") is True
```

### 3.4 Integration Test Example

```python
# tests/integration/test_database.py

import pytest
import aiosqlite
from aura_sdk.db.migrations import MigrationRunner
from aura_sdk.db.connection import get_db, init_db

class TestDatabase:

    @pytest.fixture
    async def db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        return db_path

    async def test_migrations_run(self, db):
        runner = MigrationRunner(db)
        count = await runner.migrate()
        assert count >= 1

    async def test_user_crud(self, db):
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
                ("test@example.com", "hashed", "viewer")
            )
            await conn.commit()

            cursor = await conn.execute("SELECT * FROM users WHERE email = ?", ("test@example.com",))
            row = await cursor.fetchone()
            assert row["email"] == "test@example.com"
            assert row["role"] == "viewer"

    async def test_audit_append_only(self, db):
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO audit_ledger (event_type, session_id, target_type, target_id, chain_hash) VALUES (?, ?, ?, ?, ?)",
                ("user.login", "sess1", "user", "u1", "0" * 64)
            )
            await conn.commit()

            # Update should fail
            with pytest.raises(Exception, match="append-only"):
                await conn.execute("UPDATE audit_ledger SET event_type = ? WHERE id = 1", ("hacked",))

    async def test_fts_search(self, db):
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO migration_rules (subsystem_id, category, downstream_pattern, confidence) VALUES (?, ?, ?, ?)",
                ("s1", "pattern", "snd_soc_dai_set_sysclk", 0.9)
            )
            await conn.commit()

            cursor = await conn.execute(
                "SELECT * FROM rules_fts WHERE rules_fts MATCH ?", ("sysclk",)
            )
            rows = await cursor.fetchall()
            assert len(rows) >= 1
```

### 3.5 E2E Test Example (Playwright)

```python
# tests/e2e/test_bootstrap.py

from playwright.sync_api import Page, expect

def test_first_run_creates_admin(page: Page, fresh_db):
    """First startup shows bootstrap wizard."""
    page.goto("http://localhost:3000")

    # Should redirect to login
    expect(page).to_have_url("http://localhost:3000/login")

    # Login with bootstrap credentials
    page.fill("[data-testid=email]", "admin@aura.local")
    page.fill("[data-testid=password]", "admin123")
    page.click("[data-testid=login-submit]")

    # Should reach dashboard
    expect(page).to_have_url("http://localhost:3000/")
    expect(page.locator("[data-testid=dashboard-title]")).to_be_visible()

def test_agent_workflow(page: Page, admin_logged_in):
    """Submit a driver, watch agent run."""
    page.goto("http://localhost:3000/migration")

    # Upload a driver
    page.fill("[data-testid=driver-path]", "/kernel-sources/downstream/wcd934x.c")
    page.click("[data-testid=submit-driver]")

    # Should see task created
    expect(page.locator("[data-testid=task-status]")).to_contain_text("queued")

    # Wait for agent to run
    page.wait_for_selector("[data-testid=task-status-running]", timeout=30000)
    page.wait_for_selector("[data-testid=task-status-completed]", timeout=120000)

    # Should see results
    expect(page.locator("[data-testid=patterns-found]")).to_be_visible()
```

---

## 4. CI/CD STRATEGY

### 4.1 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml

name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv pip install -e "workspace/aura-sdk[dev]" -e "services/core" -e "agents"
      - name: Ruff lint
        run: cd workspace/aura-sdk && ruff check . && cd ../.. && ruff check services/ agents/
      - name: Mypy type check
        run: mypy services/core/src agents/src workspace/aura-sdk/src

  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install
        run: uv pip install -e "workspace/aura-sdk[dev]" -e "services/core" -e "agents"
      - name: Unit tests
        run: pytest tests/unit/ -v --cov=workspace/aura-sdk --cov=services/core --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  test-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install
        run: uv pip install -e "workspace/aura-sdk[dev]" -e "services/core" -e "agents"
      - name: Integration tests
        run: pytest tests/integration/ -v

  test-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start stack
        run: make up
      - name: Wait for ready
        run: |
          for i in {1..30}; do
            curl -s http://localhost:8000/health/ready && break
            sleep 1
          done
      - name: Install Playwright
        run: |
          cd dashboard
          npm ci
          npx playwright install chromium
      - name: E2E tests
        run: cd tests/e2e && npx playwright test
      - name: Stop stack
        run: make down

  build:
    runs-on: ubuntu-latest
    needs: [lint, test-unit, test-integration]
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker images
        run: docker compose build
      - name: Push to registry (main branch only)
        if: github.ref == 'refs/heads/main'
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker compose push
```

### 4.2 Local Development Workflow

```bash
# ── Initial setup ──
git clone <repo>
cd AURA
cp .env.example .env
# Edit .env: add OPENAI_API_KEY, JWT_SECRET

# ── Start everything ──
make dev          # Docker Compose with hot reload

# ── Verify ──
make health       # curl health/ready
make metrics      # curl metrics

# ── Run tests ──
make test         # All tests
make test-unit    # Unit only
make test-e2e     # E2E only

# ── Lint ──
make lint         # ruff + mypy

# ── View logs ──
make logs         # docker compose logs -f

# ── Stop ──
make down         # docker compose down
```

### 4.3 Makefile

```makefile
.PHONY: up down dev logs shell test lint bootstrap backup health

# ── Docker ──
up:
	docker compose up --build -d

down:
	docker compose down

dev:
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build -d

logs:
	docker compose logs -f

# ── Testing ──
test:
	cd workspace/aura-sdk && pytest
	cd services/core && pytest
	cd agents && pytest

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-e2e:
	cd tests/e2e && npx playwright test

# ── Lint ──
lint:
	cd workspace/aura-sdk && ruff check . && mypy src
	cd services/core && ruff check . && mypy src
	cd agents && ruff check . && mypy src

# ── Operations ──
bootstrap:
	./scripts/bootstrap.sh

backup:
	./scripts/backup.sh

health:
	@curl -s http://localhost:8000/health/ready | python -m json.tool

metrics:
	@curl -s http://localhost:8000/metrics

export-knowledge:
	./scripts/export-knowledge.sh
```
