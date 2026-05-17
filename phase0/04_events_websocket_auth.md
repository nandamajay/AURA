# AURA Phase 0 — Event Bus, WebSocket Architecture & Authentication Bootstrap
## Implementation-Grade Blueprint | Artifact P0-4
### Status: READY FOR IMPLEMENTATION

---

## 1. EVENT BUS CONTRACTS

### 1.1 Event Taxonomy (Complete)

```python
# aura_sdk/models/event.py

from enum import StrEnum

class EventType(StrEnum):
    # ── Service Lifecycle ──
    SERVICE_STARTED = "service.started"
    SERVICE_STOPPED = "service.stopped"
    SERVICE_HEALTHY = "service.healthy"
    SERVICE_DEGRADED = "service.degraded"

    # ── Agent Lifecycle (8 types) ──
    AGENT_REGISTERED = "agent.registered"
    AGENT_SPAWNED = "agent.spawned"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_TIMEOUT = "agent.timeout"
    AGENT_KILLED = "agent.killed"
    AGENT_PROGRESS = "agent.progress"

    # ── Task Orchestration (6 types) ──
    TASK_CREATED = "task.created"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_CANCELLED = "task.cancelled"

    # ── Simulation (4 types) ──
    SIM_STARTED = "sim.started"
    SIM_PROGRESS = "sim.progress"
    SIM_COMPLETED = "sim.completed"
    SIM_FAILED = "sim.failed"

    # ── Governance (5 types) ──
    APPROVAL_REQUIRED = "governance.approval_required"
    APPROVAL_GRANTED = "governance.approval_granted"
    APPROVAL_REJECTED = "governance.approval_rejected"
    ESCALATION_TRIGGERED = "governance.escalation_triggered"
    AUDIT_EVENT = "governance.audit"

    # ── LLM Gateway (4 types) ──
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"
    LLM_CACHE_HIT = "llm.cache_hit"

    # ── Circuit Breaker (1 type) ──
    CIRCUIT_BREAKER_STATE = "circuit_breaker.state"
```

### 1.2 Event Envelope Schema (Immutable Contract)

```json
{
    "event_id": "uuid-v4",
    "event_type": "agent.spawned",
    "timestamp": "2026-05-15T10:30:00.000Z",
    "source": {
        "subsystem": "S1",
        "service": "core",
        "agent_type": "learning",
        "agent_id": "uuid",
        "task_id": "uuid"
    },
    "payload": {
        "pid": 1234,
        "rules_path": "/rules/learning.md",
        "priority": 1
    },
    "trace_id": "uuid-v4",
    "version": "1.0"
}
```

### 1.3 Event Channel Subscriptions

```
Channel: agent.lifecycle
    Subscribers:
        - ws-server (broadcast to dashboard)
        - orchestrator (track state)
        - audit (log to audit_ledger)

Channel: task.orchestration
    Subscribers:
        - ws-server (broadcast)
        - scheduler (track queue depth)
        - dashboard metrics

Channel: simulation
    Subscribers:
        - ws-server (broadcast)
        - orchestrator (update patch confidence)

Channel: governance
    Subscribers:
        - ws-server (broadcast)
        - approval engine (trigger workflows)
        - escalation engine (check triggers)
        - audit (log)

Channel: llm
    Subscribers:
        - cost tracker (budget enforcement)
        - metrics (token usage)

Channel: circuit_breaker
    Subscribers:
        - ws-server (dashboard alert)
        - scheduler (skip broken agents)
```

### 1.4 Event Bus Implementation (In-Memory MVP)

```python
# aura_sdk/bus/event_bus.py

import asyncio
import uuid
from datetime import datetime
from typing import Callable, Awaitable, Optional
from collections import defaultdict

from aura_sdk.models.event import EventEnvelope, EventType, EventSource

EventHandler = Callable[[EventEnvelope], Awaitable[None]]

class EventBus:
    """
    In-memory async event bus. Zero external dependencies.
    Designed to be replaced with Redis/RabbitMQ later without
    changing subscriber code.
    
    Guarantees:
    - At-most-once delivery (events can be dropped on crash)
    - Ordered within a channel
    - Non-blocking publish (queue with backpressure)
    - Never crashes subscribers (exceptions caught and logged)
    """

    def __init__(self, max_queue_size: int = 10000):
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._all_handlers: list[EventHandler] = []
        self._queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=max_queue_size)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._dropped_count = 0

    # ── Lifecycle ──

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatcher(), name="event-bus")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        # Drain remaining events
        await self._queue.join()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── Subscription ──

    def subscribe(self, event_type: EventType, handler: EventHandler):
        """Subscribe to a specific event type."""
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler):
        """Subscribe to ALL event types."""
        self._all_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        """Unsubscribe handler."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    # ── Publishing ──

    async def publish(self, event: EventEnvelope) -> bool:
        """Publish event. Returns False if queue full (backpressure)."""
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped_count += 1
            return False

    # ── Internal ──

    async def _dispatcher(self):
        """Main dispatch loop. Never crashes."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_one(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _dispatch_one(self, event: EventEnvelope):
        """Dispatch to all relevant handlers. Each handler is independent."""
        handlers = self._handlers.get(event.event_type, []) + self._all_handlers

        if not handlers:
            return

        # Run handlers concurrently, but catch all exceptions
        results = await asyncio.gather(
            *[self._safe_handle(h, event) for h in handlers],
            return_exceptions=True
        )

        # Log failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Event handler {i} failed for {event.event_type}: {result}")

    async def _safe_handle(self, handler: EventHandler, event: EventEnvelope):
        """Call handler, never propagate exceptions."""
        try:
            await handler(event)
        except Exception as e:
            # Log but don't crash
            print(f"Handler error: {e}")

    # ── Observability ──

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def subscriber_counts(self) -> dict[str, int]:
        return {t.value: len(h) for t, h in self._handlers.items()}
```

### 1.5 Event Persistence (Buffer for Replay)

```python
class EventBuffer:
    """Ring buffer of recent events for replay on reconnect."""

    def __init__(self, max_size: int = 10000):
        self._buffer: deque[EventEnvelope] = deque(maxlen=max_size)

    def append(self, event: EventEnvelope):
        self._buffer.append(event)

    def get_since(self, event_id: str) -> list[EventEnvelope]:
        """Return all events after the given event_id."""
        found = False
        result = []
        for event in self._buffer:
            if found:
                result.append(event)
            if event.event_id == event_id:
                found = True
        return result

    def get_recent(self, count: int = 100) -> list[EventEnvelope]:
        return list(self._buffer)[-count:]
```

---

## 2. QUEUE & RETRY SEMANTICS

### 2.1 Task Queue Implementation

```python
# core/services/scheduler.py

import asyncio
from collections import deque
from enum import IntEnum
from datetime import datetime, timedelta
from typing import Optional

class TaskPriority(IntEnum):
    P0_CRITICAL = 0     # Governance, circuit breaker triggers — FIFO
    P1_NORMAL = 1       # Migration, validation — Round-robin
    P2_BACKGROUND = 2   # Learning — Best effort

class TaskQueue:
    """
    Priority queue with 3 tiers.
    - P0: Critical tasks (governance, escalations). FIFO.
    - P1: Normal tasks (migration, validation). Round-robin by agent type.
    - P2: Background tasks (learning). Only runs when load < 50%.
    
    Guarantees:
    - P0 never starved
    - P1 gets fair share across agent types
    - P2 never blocks P0 or P1
    """

    def __init__(self, max_size: int = 10000):
        self._p0: deque[Task] = deque()  # Critical — FIFO
        self._p1: dict[str, deque[Task]] = {}  # Normal — by agent type
        self._p1_order: list[str] = []  # Round-robin order
        self._p1_index = 0  # Current position in round-robin
        self._p2: deque[Task] = deque()  # Background
        self._in_progress: dict[str, Task] = {}
        self._completed: deque[Task] = deque(maxlen=10000)
        self._max_concurrent = 50

    # ── Enqueue ──

    def enqueue(self, task: Task) -> bool:
        if task.priority == TaskPriority.P0_CRITICAL:
            self._p0.append(task)
        elif task.priority == TaskPriority.P1_NORMAL:
            agent_type = task.agent_type
            if agent_type not in self._p1:
                self._p1[agent_type] = deque()
                self._p1_order.append(agent_type)
            self._p1[agent_type].append(task)
        else:
            self._p2.append(task)
        return True

    # ── Dequeue ──

    def dequeue(self) -> Optional[Task]:
        # P0 first (never starved)
        if self._p0:
            return self._start(self._p0.popleft())

        # P1 round-robin
        task = self._dequeue_p1_round_robin()
        if task:
            return self._start(task)

        # P2 only if load < 50%
        if self.load_factor < 0.5 and self._p2:
            return self._start(self._p2.popleft())

        return None

    def _dequeue_p1_round_robin(self) -> Optional[Task]:
        if not self._p1_order:
            return None

        # Try each agent type in round-robin order
        for _ in range(len(self._p1_order)):
            agent_type = self._p1_order[self._p1_index]
            self._p1_index = (self._p1_index + 1) % len(self._p1_order)

            if self._p1.get(agent_type):
                return self._p1[agent_type].popleft()

        return None

    # ── Task State Management ──

    def _start(self, task: Task) -> Task:
        task.status = "running"
        task.started_at = datetime.utcnow()
        self._in_progress[task.id] = task
        return task

    def complete(self, task_id: str):
        task = self._in_progress.pop(task_id, None)
        if task:
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            self._completed.append(task)

    def fail(self, task_id: str, reason: str):
        task = self._in_progress.pop(task_id, None)
        if task:
            task.status = "failed"
            task.failure_reason = reason
            self._completed.append(task)

    # ── Observability ──

    @property
    def load_factor(self) -> float:
        return len(self._in_progress) / self._max_concurrent

    @property
    def p0_depth(self) -> int:
        return len(self._p0)

    @property
    def p1_depth(self) -> int:
        return sum(len(q) for q in self._p1.values())

    @property
    def p2_depth(self) -> int:
        return len(self._p2)

    @property
    def stats(self) -> dict:
        return {
            "p0_depth": self.p0_depth,
            "p1_depth": self.p1_depth,
            "p2_depth": self.p2_depth,
            "in_progress": len(self._in_progress),
            "completed_total": len(self._completed),
            "load_factor": round(self.load_factor, 2),
            "max_concurrent": self._max_concurrent,
        }
```

### 2.2 Retry Semantics

```python
# core/services/retry_policy.py

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Callable
import asyncio

class ExitCode(IntEnum):
    SUCCESS = 0
    VALIDATION_FAILED = 1
    UNRECOVERABLE = 2
    TIMEOUT = 3
    RESOURCE_EXHAUSTED = 4
    LLM_UNAVAILABLE = 5

@dataclass
class RetryPolicy:
    """Retry configuration per exit code."""
    max_retries: int
    backoff_seconds: list[float]  # [5.0, 15.0, 45.0] for 3 retries
    retryable: bool

DEFAULT_POLICIES: dict[ExitCode, RetryPolicy] = {
    ExitCode.SUCCESS: RetryPolicy(0, [], False),
    ExitCode.VALIDATION_FAILED: RetryPolicy(0, [], False),  # Never retry
    ExitCode.UNRECOVERABLE: RetryPolicy(0, [], False),      # Never retry
    ExitCode.TIMEOUT: RetryPolicy(3, [5.0, 15.0, 45.0], True),
    ExitCode.RESOURCE_EXHAUSTED: RetryPolicy(2, [30.0, 120.0], True),
    ExitCode.LLM_UNAVAILABLE: RetryPolicy(5, [5.0, 15.0, 45.0, 60.0, 60.0], True),
}

class RetryExecutor:
    """Executes tasks with retry logic."""

    def __init__(self, policies: dict[ExitCode, RetryPolicy] = None):
        self._policies = policies or DEFAULT_POLICIES
        self._attempts: dict[str, int] = {}  # task_id -> attempt count

    async def execute(
        self,
        task: Task,
        executor: Callable[[Task], Awaitable[ExitCode]]
    ) -> ExitCode:
        task_id = task.id
        self._attempts[task_id] = 0

        while True:
            self._attempts[task_id] += 1
            attempt = self._attempts[task_id]

            exit_code = await executor(task)

            if exit_code == ExitCode.SUCCESS:
                del self._attempts[task_id]
                return exit_code

            policy = self._policies.get(exit_code)
            if not policy or not policy.retryable:
                del self._attempts[task_id]
                return exit_code  # Terminal failure

            if attempt > policy.max_retries:
                del self._attempts[task_id]
                return exit_code  # Max retries exceeded

            # Retry with backoff
            backoff = policy.backoff_seconds[min(attempt - 1, len(policy.backoff_seconds) - 1)]
            await asyncio.sleep(backoff)
```

---

## 3. WEBSOCKET ARCHITECTURE

### 3.1 Connection Manager

```python
# ws-server/connection_manager.py

import asyncio
from typing import Optional
from fastapi import WebSocket

class ConnectionManager:
    """Manages WebSocket connections with heartbeat and reconnection support."""

    def __init__(self, max_connections: int = 100):
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[str]] = {}  # channel -> {connection_ids}
        self._max_connections = max_connections
        self._heartbeat_interval = 30  # seconds

    async def connect(self, websocket: WebSocket) -> Optional[str]:
        if len(self._connections) >= self._max_connections:
            await websocket.close(code=1008, reason="Server capacity reached")
            return None

        await websocket.accept()
        conn_id = str(uuid4())
        self._connections[conn_id] = websocket
        return conn_id

    async def disconnect(self, conn_id: str):
        ws = self._connections.pop(conn_id, None)
        if ws:
            # Clean up subscriptions
            for channel in list(self._subscriptions.keys()):
                self._subscriptions[channel].discard(conn_id)

    async def subscribe(self, conn_id: str, channels: list[str]):
        for channel in channels:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = set()
            self._subscriptions[channel].add(conn_id)

    async def unsubscribe(self, conn_id: str, channels: list[str]):
        for channel in channels:
            if channel in self._subscriptions:
                self._subscriptions[channel].discard(conn_id)

    async def broadcast_to_channel(self, channel: str, message: str):
        """Send to all subscribers of a channel."""
        conn_ids = self._subscriptions.get(channel, set())
        dead = []
        for conn_id in conn_ids:
            ws = self._connections.get(conn_id)
            if ws:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(conn_id)
            else:
                dead.append(conn_id)
        # Clean up dead connections
        for conn_id in dead:
            await self.disconnect(conn_id)

    async def send_to(self, conn_id: str, message: str):
        ws = self._connections.get(conn_id)
        if ws:
            await ws.send_text(message)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def subscription_counts(self) -> dict[str, int]:
        return {ch: len(ids) for ch, ids in self._subscriptions.items()}
```

### 3.2 WebSocket Endpoint

```python
# ws-server/ws_endpoint.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    conn_id = await manager.connect(websocket)
    if not conn_id:
        return

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "subscribe":
                channels = msg.get("channels", [])
                await manager.subscribe(conn_id, channels)
                await manager.send_to(conn_id, json.dumps({"action": "subscribed", "channels": channels}))

            elif action == "unsubscribe":
                channels = msg.get("channels", [])
                await manager.unsubscribe(conn_id, channels)

            elif action == "ping":
                await manager.send_to(conn_id, json.dumps({"action": "pong", "timestamp": time.time()}))

    except WebSocketDisconnect:
        await manager.disconnect(conn_id)
    except Exception:
        await manager.disconnect(conn_id)
```

### 3.3 SSE Fallback Endpoint

```python
# ws-server/sse_endpoint.py

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.get("/events")
async def events_sse(request: Request):
    """SSE fallback for clients that can't use WebSocket."""
    async def event_stream():
        # Send buffered events first
        for event in event_buffer.get_recent(100):
            yield f"event: {event.event_type}\ndata: {event.to_json()}\n\n"

        # Then stream new events
        queue = asyncio.Queue()
        async def listener(evt):
            await queue.put(evt)
        event_bus.subscribe_all(listener)

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"event: {event.event_type}\ndata: {event.to_json()}\n\n"
        except asyncio.TimeoutError:
            yield f"event: ping\ndata: {{}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
```

### 3.4 Dashboard WebSocket Client (React)

```typescript
// dashboard/src/hooks/useWebSocket.ts

import { useEffect, useRef, useCallback, useState } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8001/ws';
const RECONNECT_BASE = 1000;   // 1s
const RECONNECT_MAX = 30000;   // 30s
const HEARTBEAT_INTERVAL = 25000; // 25s (shorter than server 30s)

interface UseWebSocketOptions {
  channels?: string[];
  onEvent?: (event: AuraEvent) => void;
}

export function useWebSocket({ channels = [], onEvent }: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval>>();

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttempt.current = 0;
      // Subscribe to channels
      ws.send(JSON.stringify({ action: 'subscribe', channels }));
      // Start heartbeat
      heartbeatTimer.current = setInterval(() => {
        ws.send(JSON.stringify({ action: 'ping' }));
      }, HEARTBEAT_INTERVAL);
    };

    ws.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      if (data.action === 'pong') return;
      if (data.event_id) setLastEventId(data.event_id);
      onEvent?.(data);
    };

    ws.onclose = () => {
      setIsConnected(false);
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
      // Exponential reconnect
      const delay = Math.min(
        RECONNECT_BASE * 2 ** reconnectAttempt.current,
        RECONNECT_MAX
      );
      reconnectAttempt.current++;
      setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [channels, onEvent]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
    };
  }, [connect]);

  return { isConnected, lastEventId };
}
```

---

## 4. AUTHENTICATION BOOTSTRAP

### 4.1 First-Run Wizard

```python
# core/services/bootstrap.py

import bcrypt
import sqlite3
from datetime import datetime

class BootstrapWizard:
    """
    5-minute first-run setup.
    Detects empty database, creates admin account, validates environment.
    """

    REQUIRED_ENV = [
        "JWT_SECRET",
        "OPENAI_API_KEY",
    ]

    OPTIONAL_ENV_WITH_DEFAULTS = {
        "ADMIN_EMAIL": "admin@aura.local",
        "ADMIN_PASSWORD": None,  # Will prompt if not set
        "SQLITE_PATH": "./data/aura.db",
        "MAX_CONCURRENT_AGENTS": "50",
        "AGENT_TIMEOUT_SECONDS": "300",
        "TOKEN_BUDGET_DAILY": "1000000",
    }

    async def run(self) -> BootstrapResult:
        results = []

        # Step 1: Check environment
        results.append(self._check_env())

        # Step 2: Validate database
        results.append(await self._init_database())

        # Step 3: Create admin user (if no users exist)
        results.append(await self._create_admin())

        # Step 4: Validate LLM connection
        results.append(await self._validate_llm())

        # Step 5: Validate kernel sources
        results.append(self._validate_kernel_sources())

        return BootstrapResult(results)

    def _check_env(self) -> CheckResult:
        missing = [k for k in self.REQUIRED_ENV if not os.getenv(k)]
        if missing:
            return CheckResult.fail("env", f"Missing required: {', '.join(missing)}")
        return CheckResult.pass_("env", f"All {len(self.REQUIRED_ENV)} required variables set")

    async def _init_database(self) -> CheckResult:
        from aura_sdk.db.migrations import MigrationRunner
        runner = MigrationRunner(os.getenv("SQLITE_PATH"))
        count = await runner.migrate()
        return CheckResult.pass_("database", f"Ran {count} migrations")

    async def _create_admin(self) -> CheckResult:
        async with get_db() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            count = (await cursor.fetchone())[0]

            if count > 0:
                return CheckResult.pass_("admin", "Users already exist, skipping")

            # Create admin
            email = os.getenv("ADMIN_EMAIL", "admin@aura.local")
            password = os.getenv("ADMIN_PASSWORD") or self._generate_password()
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

            await db.execute(
                """INSERT INTO users (email, password_hash, role, display_name)
                   VALUES (?, ?, 'admin', 'Administrator')""",
                (email, hashed)
            )
            await db.commit()

            return CheckResult.pass_(
                "admin",
                f"Created admin: {email} / {password} (change this password!)"
            )

    async def _validate_llm(self) -> CheckResult:
        import httpx
        gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8000")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{gateway_url}/health")
                if resp.status_code == 200:
                    return CheckResult.pass_("llm", "LLM gateway reachable")
                return CheckResult.fail("llm", f"Gateway returned {resp.status_code}")
        except Exception as e:
            return CheckResult.fail("llm", f"Cannot reach gateway: {e}")

    def _validate_kernel_sources(self) -> CheckResult:
        path = os.getenv("KERNEL_SOURCES_PATH", "")
        if not path:
            return CheckResult.warn("kernel", "No kernel sources mounted. Provide KERNEL_SOURCES_PATH to enable migration.")
        if not os.path.exists(path):
            return CheckResult.fail("kernel", f"Path not found: {path}")
        return CheckResult.pass_("kernel", f"Kernel sources mounted at {path}")

    def _generate_password(self) -> str:
        import secrets
        return secrets.token_urlsafe(12)
```

### 4.2 JWT Authentication

```python
# governance/auth/jwt.py

import jwt
from datetime import datetime, timedelta
from typing import Optional

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

class JWTManager:
    def __init__(self, secret: str):
        self._secret = secret

    def create_token(self, user_id: str, email: str, role: str) -> str:
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self._secret, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

# FastAPI dependency
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    payload = jwt_mgr.verify_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload

async def require_role(role: str):
    async def checker(payload: dict = Depends(require_auth)):
        if payload.get("role") not in [role, "admin"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {role}")
        return payload
    return checker
```

### 4.3 RBAC Enforcer

```python
# governance/rbac/enforcer.py

from enum import StrEnum

class Permission(StrEnum):
    VIEW_DASHBOARD = "view:dashboard"
    VIEW_PATCHES = "view:patches"
    COMMENT_PATCH = "comment:patch"
    REQUEST_REWORK = "rework:patch"
    APPROVE_OWN = "approve:own"
    APPROVE_ANY = "approve:any"
    ARCHITECT_OVERRIDE = "architect:override"
    MANAGE_USERS = "manage:users"
    MANAGE_SUBSYSTEMS = "manage:subsystems"
    EXPORT_AUDIT = "export:audit"
    CONFIGURE_LLM = "configure:llm"

ROLE_PERMISSIONS = {
    "viewer": [
        Permission.VIEW_DASHBOARD, Permission.VIEW_PATCHES,
    ],
    "reviewer": [
        Permission.VIEW_DASHBOARD, Permission.VIEW_PATCHES,
        Permission.COMMENT_PATCH, Permission.REQUEST_REWORK,
    ],
    "approver": [
        Permission.VIEW_DASHBOARD, Permission.VIEW_PATCHES,
        Permission.COMMENT_PATCH, Permission.REQUEST_REWORK,
        Permission.APPROVE_OWN,
    ],
    "architect": [
        Permission.VIEW_DASHBOARD, Permission.VIEW_PATCHES,
        Permission.COMMENT_PATCH, Permission.REQUEST_REWORK,
        Permission.APPROVE_ANY, Permission.ARCHITECT_OVERRIDE,
        Permission.MANAGE_SUBSYSTEMS, Permission.EXPORT_AUDIT,
    ],
    "admin": list(Permission),  # All permissions
}

class RBACEnforcer:
    def has_permission(self, role: str, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(role, [])

    def get_permissions(self, role: str) -> list[Permission]:
        return list(ROLE_PERMISSIONS.get(role, []))
```

---

## 5. HEALTH CHECK FRAMEWORK

```python
# core/routers/health.py

from fastapi import APIRouter, Response, status
import psutil
import os
import httpx

router = APIRouter()

@router.get("/health/live")
async def liveness() -> dict:
    """Kubernetes-style liveness probe.
    Returns 200 if process is alive."""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Kubernetes-style readiness probe.
    Returns 200 only if ALL dependencies are healthy."""
    checks = {}

    # Check 1: SQLite
    try:
        async with get_db() as db:
            await db.execute("SELECT 1")
        checks["database"] = {"healthy": True, "detail": "Connected"}
    except Exception as e:
        checks["database"] = {"healthy": False, "detail": str(e)}

    # Check 2: LLM Gateway
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.LLM_GATEWAY_URL}/health")
        checks["llm_gateway"] = {
            "healthy": resp.status_code == 200,
            "detail": f"HTTP {resp.status_code}"
        }
    except Exception as e:
        checks["llm_gateway"] = {"healthy": False, "detail": str(e)}

    # Check 3: Disk space
    disk = psutil.disk_usage("/data")
    disk_ok = disk.free > 10 * 1024 * 1024 * 1024  # 10GB
    checks["disk"] = {
        "healthy": disk_ok,
        "detail": f"{disk.free // (1024**3)}GB free"
    }

    # Check 4: Memory
    mem = psutil.virtual_memory()
    mem_ok = mem.available > 2 * 1024 * 1024 * 1024  # 2GB
    checks["memory"] = {
        "healthy": mem_ok,
        "detail": f"{mem.available // (1024**2)}MB available"
    }

    all_healthy = all(c["healthy"] for c in checks.values())
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## 6. LOGGING ARCHITECTURE

```python
# aura_sdk/logging/logger.py

import structlog
import logging
import sys
from pathlib import Path

LOG_DIR = Path("./data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def configure_logging(service_name: str, log_level: str = "INFO"):
    """Configure structured JSON logging for a service."""

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, log_level))

    # File handler (rotating)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        LOG_DIR / f"{service_name}.jsonl",
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=10,
    )
    file_handler.setLevel(logging.DEBUG)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level))
    root.handlers = [console_handler, file_handler]

def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
```

**Log format (JSON Lines):**
```json
{"timestamp":"2026-05-15T10:30:00.123Z","level":"info","service":"core","agent_type":"learning","task_id":"uuid","event":"agent_spawned","message":"Agent started","pid":1234}
```

---

## 7. METRICS ARCHITECTURE

```python
# core/routers/health.py (continued)

from collections import Counter

# In-memory counters (replaced with prometheus_client if needed later)
_counters: Counter = Counter()
_gauges: dict[str, float] = {}

@router.get("/metrics")
async def metrics() -> str:
    """Prometheus-compatible text format."""
    lines = []
    lines.append("# HELP aura_agents_total Current agents by state")
    lines.append("# TYPE aura_agents_total gauge")
    for state, count in _gauges.items():
        if state.startswith("agent_"):
            lines.append(f'aura_agents_total{{state="{state}"}} {count}')

    lines.append("# HELP aura_task_queue_depth Current queue depth by priority")
    lines.append("# TYPE aura_task_queue_depth gauge")
    lines.append(f'aura_task_queue_depth{{priority="p0"}} {queue.p0_depth}')
    lines.append(f'aura_task_queue_depth{{priority="p1"}} {queue.p1_depth}')
    lines.append(f'aura_task_queue_depth{{priority="p2"}} {queue.p2_depth}')

    lines.append("# HELP aura_llm_tokens_total Total LLM tokens used")
    lines.append("# TYPE aura_llm_tokens_total counter")
    for key, count in _counters.items():
        if key.startswith("llm_tokens_"):
            lines.append(f'aura_llm_tokens_total{{provider="openai"}} {count}')

    return "\n".join(lines)
```
