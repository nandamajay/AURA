# AURA Platform — Infrastructure, Persistence, Queue, Sandbox, Observability & Governance
## Artifacts 6-10: Deep Subsystem Specifications
### Version: 1.0 | Stage: Architecture Stabilization | Date: 2026-05-15

---

## ARTIFACT 6: Persistence & Knowledge Graph Architecture

### 6.1 Database Schema Design

#### 6.1.1 Core Tables

```sql
-- Users & Identity (Pillar A)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,  -- bcrypt
    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('viewer','reviewer','approver','architect','admin')),
    created_at INTEGER NOT NULL,  -- Unix timestamp
    last_login_at INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Subsystems (plugin registry)
CREATE TABLE subsystems (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    plugin_path TEXT NOT NULL,
    version TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    config_json TEXT  -- Plugin-specific configuration
);

-- Migration Rules (core knowledge)
CREATE TABLE migration_rules (
    id TEXT PRIMARY KEY,
    subsystem_id TEXT REFERENCES subsystems(id),
    category TEXT NOT NULL
        CHECK (category IN ('api_mapping','pattern','macro','philosophy','style')),
    pattern TEXT NOT NULL,           -- Regex or description
    upstream_equivalent TEXT,        -- What to replace with
    confidence REAL NOT NULL DEFAULT 0.5
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    source_refs TEXT,                -- JSON array of git commits
    created_at INTEGER NOT NULL,
    last_applied_at INTEGER,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0
);

-- Maintainer Intelligence
CREATE TABLE maintainer_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    subsystem_id TEXT REFERENCES subsystems(id),
    acceptance_rate REAL,
    common_nak_reasons TEXT,         -- JSON array
    preferred_patterns TEXT,         -- JSON array
    personality_model TEXT,          -- JSON object
    last_analyzed_at INTEGER
);

-- Patch Evolution
CREATE TABLE patches (
    id TEXT PRIMARY KEY,
    subsystem_id TEXT REFERENCES subsystems(id),
    version INTEGER NOT NULL DEFAULT 1,  -- v1, v2, v3...
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','migrating','validating','simulating',
                         'reviewing','approved','rejected','upstreamed')),
    confidence_score REAL,
    generated_by TEXT,               -- Agent type
    approved_by TEXT REFERENCES users(id),
    diff_path TEXT NOT NULL,         -- Path to diff file
    cover_letter_path TEXT,
    changelog_path TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Approval Ledger (immutable)
CREATE TABLE approval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patch_id TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL
        CHECK (action IN ('submit','approve','reject','request_rework',
                         'escalate','comment')),
    dimension TEXT  -- A, B, or C
        CHECK (dimension IN ('lifecycle','subsystem','quality')),
    stage TEXT NOT NULL,
    confidence_at_action REAL,
    evidence_json TEXT,              -- Snapshot of evidence
    session_id TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
-- Append-only: No UPDATE/DELETE allowed on this table

-- Evidence Links (traceability)
CREATE TABLE evidence_links (
    id TEXT PRIMARY KEY,
    patch_id TEXT REFERENCES patches(id),
    rule_id TEXT REFERENCES migration_rules(id),
    evidence_type TEXT NOT NULL
        CHECK (evidence_type IN ('reference','justification','warning','correction')),
    source_ref TEXT NOT NULL,        -- Git commit, URL, document
    source_text TEXT,                -- Relevant excerpt
    confidence REAL NOT NULL,
    created_at INTEGER NOT NULL
);

-- Learning Log (4-tier)
CREATE TABLE learning_events (
    id TEXT PRIMARY KEY,
    tier INTEGER NOT NULL
        CHECK (tier IN (1,2,3,4)),
    tier_name TEXT NOT NULL,         -- kernel_pattern, maintainer_intel,
                                     -- cross_subsystem, upstream_suitability
    event_type TEXT NOT NULL
        CHECK (event_type IN ('discovered','validated','invalidated','refined')),
    pattern_description TEXT NOT NULL,
    source_refs TEXT,                -- JSON array
    confidence_before REAL,
    confidence_after REAL,
    created_at INTEGER NOT NULL
);

-- Simulation Results
CREATE TABLE simulation_results (
    id TEXT PRIMARY KEY,
    patch_id TEXT REFERENCES patches(id),
    simulation_type TEXT NOT NULL,
    fidelity_mode TEXT NOT NULL DEFAULT 'state_machine'
        CHECK (fidelity_mode IN ('state_machine','qemu')),
    status TEXT NOT NULL
        CHECK (status IN ('passed','failed','inconclusive')),
    findings_json TEXT,              -- Detailed results
    failure_predictions TEXT,        -- JSON array of predicted failures
    confidence_impact REAL,          -- How results affected confidence
    created_at INTEGER NOT NULL
);
```

#### 6.1.2 SQLite Optimizations

```sql
-- WAL mode for concurrent reads
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = 10000;        -- ~40MB cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;     -- 256MB memory-mapped I/O

-- FTS5 for full-text search on rules and evidence
CREATE VIRTUAL TABLE migration_rules_fts USING fts5(
    pattern, upstream_equivalent,
    content='migration_rules', content_rowid='rowid'
);

CREATE TRIGGER rules_fts_insert AFTER INSERT ON migration_rules
BEGIN
    INSERT INTO migration_rules_fts(rowid, pattern, upstream_equivalent)
    VALUES (new.rowid, new.pattern, new.upstream_equivalent);
END;

-- Indexes for common queries
CREATE INDEX idx_patches_status ON patches(status);
CREATE INDEX idx_patches_subsystem ON patches(subsystem_id);
CREATE INDEX idx_rules_category ON migration_rules(category);
CREATE INDEX idx_rules_confidence ON migration_rules(confidence);
CREATE INDEX idx_evidence_patch ON evidence_links(patch_id);
CREATE INDEX idx_approval_events ON approval_events(patch_id, created_at);
CREATE INDEX idx_learning_tier ON learning_events(tier, created_at);
```

### 6.2 Knowledge Graph Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE GRAPH                              │
│                                                                  │
│   [Migration Rule] ──applies_to──► [Subsystem]                   │
│        │                              │                          │
│        │ evidence                      │ has_maintainer          │
│        ▼                              ▼                          │
│   [Evidence Link] ◄────cites──── [Maintainer Profile]           │
│        │                                                          │
│        │ supports                                                 │
│        ▼                                                          │
│   [Patch] ──validates──► [Simulation Result]                     │
│        │                              │                          │
│        │ requires_approval            │ predicts_failure        │
│        ▼                              ▼                          │
│   [Approval Event] ◄────logs──── [Learning Event]               │
│                                                                  │
│   Query patterns:                                                │
│   - "Find rules for subsystem X with confidence > 0.8"          │
│   - "Trace evidence for patch Y back to source commits"          │
│   - "What patterns failed most often?"                           │
│   - "Which maintainers accept patches with pattern Z?"           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Export Architecture

| Export Type | Format | Trigger | Destination |
|-------------|--------|---------|-------------|
| Full backup | SQLite file | Daily at 02:00 | ./data/backups/ |
| Knowledge base | JSON | On-demand or weekly | ./data/exports/ |
| Per-subsystem | JSON + CSV | On-demand | ./data/exports/ |
| Audit log | JSON | On-demand | ./data/exports/ |
| Migration rules | Markdown | On-demand | ./data/exports/rules/ |

---

## ARTIFACT 7: Queue & Scheduling Architecture

### 7.1 Task Queue Design

```python
class TaskQueue:
    """In-memory priority queue with persistence backup."""

    def __init__(self, db_path: str):
        self.p0: deque[Task] = deque()  # Critical — FIFO
        self.p1: dict[str, deque[Task]] = {}  # Normal — round-robin
        self.p2: deque[Task] = deque()  # Background — best-effort
        self.in_progress: dict[str, Task] = {}  # task_id -> Task
        self.completed: deque[Task] = deque(maxlen=10000)  # Ring buffer
        self.db = sqlite3.connect(db_path)

    def enqueue(self, task: Task) -> None:
        # Persist first (idempotent)
        self._persist_task(task)
        # Then queue in memory
        if task.priority == TaskPriority.P0_CRITICAL:
            self.p0.append(task)
        elif task.priority == TaskPriority.P1_NORMAL:
            agent_type = task.agent_type
            if agent_type not in self.p1:
                self.p1[agent_type] = deque()
            self.p1[agent_type].append(task)
        else:
            self.p2.append(task)

    def dequeue(self) -> Optional[Task]:
        # Recovery: check database for orphaned tasks
        self._recover_orphaned()
        # P0 first
        if self.p0:
            return self._start(self.p0.popleft())
        # P1 round-robin
        for agent_type in self._round_robin_order():
            if self.p1.get(agent_type):
                return self._start(self.p1[agent_type].popleft())
        # P2 only if load < 50%
        if self.load_factor < 0.5 and self.p2:
            return self._start(self.p2.popleft())
        return None

    @property
    def load_factor(self) -> float:
        return len(self.in_progress) / self.max_concurrent
```

### 7.2 Scheduling Rules

| Rule | Implementation |
|------|---------------|
| Max concurrency | 50 agents (configurable) |
| Fairness | Round-robin across P1 agent types |
| Starvation prevention | P2 guaranteed 10% of slots when queue depth > 0 |
| Priority inversion | P0 can preempt P2 (not P1) |
| Agent affinity | Same task type prefers same warm process |
| Timeout | 300s default, configurable per agent type |

### 7.3 Backpressure

```
Queue depth < 10   → Normal operation
Queue depth 10-50  → Reduce P2 scheduling
Queue depth 50-100 → Pause P2, alert dashboard
Queue depth > 100  → Pause new task creation, alert admin
Agent failures > 3 → Circuit breaker opens for that agent type
LLM errors > 5     → Switch to fallback provider
```

---

## ARTIFACT 8: Sandbox & Isolation Architecture

### 8.1 Agent Sandboxing Specification

```python
class AgentSandbox:
    """Subprocess isolation with resource limits and security constraints."""

    async def spawn(
        self,
        agent_type: str,
        task_id: str,
        rules_path: str,
        resource_limits: ResourceLimits = None
    ) -> subprocess.Popen:
        # Working directory: isolated per task
        work_dir = f"{self.tmp_base}/{task_id}"
        os.makedirs(work_dir, exist_ok=True)

        # Build command
        cmd = [
            "python", "-m", f"agents.{agent_type}",
            "--task-id", task_id,
            "--rules", rules_path,
            "--output-dir", work_dir,
            "--llm-gateway", self.llm_gateway_url,
        ]

        # Subprocess with limits
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Resource limits via ulimit
            limit=resource_limits or ResourceLimits(
                cpu_cores=2,
                memory_mb=4096,
                file_descriptors=100,
                max_processes=10,
            ),
            # Security
            user="aura-agent",  # non-root
            # Environment: only whitelisted vars
            env={
                "LLM_GATEWAY_URL": self.llm_gateway_url,
                "TASK_ID": task_id,
                "OUTPUT_DIR": work_dir,
                "PYTHONPATH": "/app",
            }
        )
        return proc
```

### 8.2 Resource Limits per Agent

| Resource | Limit | Enforcement | Action on Exceed |
|----------|-------|-------------|-----------------|
| CPU | 2 cores | cgroups | Throttle (not kill) |
| Memory | 4 GB | cgroups OOM | SIGKILL + retry |
| File descriptors | 100 | ulimit | EMFILE error |
| Processes | 10 | ulimit | EAGAIN error |
| Disk (temp) | 1 GB | quota | ENOSPC error |
| Network | None | seccomp | Agents use LLM gateway only |
| Execution time | 300s default | watchdog timer | SIGTERM → SIGKILL |

### 8.3 Security Layers

| Layer | Technology | Scope |
|-------|-----------|-------|
| Process isolation | Subprocess | Per-agent |
| User isolation | Linux user (uid 1000) | All agents |
| Filesystem isolation | Chroot + read-only mounts | Kernel sources |
| Syscall filtering | seccomp-bpf | Deny exec, bind, connect |
| Resource limits | cgroups | CPU, memory, I/O |
| Network isolation | Docker network | No external access |
| Secret isolation | Docker secrets | API keys |

### 8.4 seccomp-bpf Policy

```python
# Allowed syscalls for agents
ALLOWED_SYSCALLS = {
    # File operations
    "read", "write", "open", "openat", "close",
    "lseek", "pread64", "pwrite64", "stat", "fstat",
    "access", "faccessat", "getdents", "getdents64",
    # Memory
    "mmap", "mprotect", "munmap", "brk",
    # Process
    "exit", "exit_group", "getpid", "getppid",
    # Signals
    "rt_sigaction", "rt_sigreturn", "kill", "tkill",
    # Time
    "clock_gettime", "gettimeofday", "nanosleep",
    # Networking (read-only to LLM gateway)
    "socket", "connect", "sendto", "recvfrom",
    # Threading
    "clone", "futex", "set_robust_list",
}

# Denied syscalls (always blocked)
DENIED_SYSCALLS = {
    "execve", "execveat",     # No code execution
    "bind", "listen",         # No incoming connections
    "ptrace",                 # No process debugging
    "mount", "umount",        # No filesystem changes
    "setuid", "setgid",       # No privilege escalation
    "reboot", "kexec_load",   # No system control
}
```

---

## ARTIFACT 9: Observability Stack Design

### 9.1 Metrics Specification

All metrics exposed at `/metrics` endpoint in Prometheus text format.

```
# Gauge: Current agents by state
aura_agents_total{state="running"} 12
aura_agents_total{state="queued"} 5
aura_agents_total{state="completed"} 147
aura_agents_total{state="failed"} 3

# Counter: Completed tasks by agent type
aura_agent_completions_total{agent_type="learning"} 23
aura_agent_completions_total{agent_type="refactor"} 45

# Counter: Failed tasks
aura_agent_failures_total{agent_type="validation",error="timeout"} 2

# Counter: LLM token usage
aura_llm_tokens_total{provider="openai",agent_type="learning"} 154000
aura_llm_tokens_total{provider="anthropic",agent_type="reviewer"} 87000

# Counter: Estimated cost
aura_llm_cost_dollars_total{provider="openai"} 2.45
aura_llm_cost_dollars_total{provider="anthropic"} 1.23

# Gauge: Queue depth
aura_task_queue_depth{priority="p0"} 0
aura_task_queue_depth{priority="p1"} 8
aura_task_queue_depth{priority="p2"} 15

# Counter: Simulation runs
aura_simulation_runs_total{sim_type="probe_flow",fidelity="state_machine"} 45
aura_simulation_runs_total{sim_type="dapm",fidelity="qemu"} 3

# Gauge: Circuit breaker states
aura_circuit_breaker_state{agent_type="refactor"} 0  # 0=closed, 1=open, 2=half_open

# Counter: Governance decisions
aura_governance_decisions_total{action="approve",dimension="lifecycle"} 12
aura_governance_decisions_total{action="reject",dimension="quality"} 3
```

### 9.2 Logging Specification

```json
{
  "timestamp": "2026-05-15T10:30:00.123Z",
  "level": "INFO",
  "logger": "aura.orchestrator.scheduler",
  "trace_id": "uuid",
  "span_id": "uuid",
  "agent_id": "uuid",
  "agent_type": "learning",
  "task_id": "uuid",
  "message": "Agent completed successfully",
  "context": {
    "patterns_found": 15,
    "confidence": 0.92,
    "duration_ms": 45000
  }
}
```

| Level | Usage | Retention |
|-------|-------|-----------|
| DEBUG | Agent internal logic | 7 days |
| INFO | Task lifecycle, state changes | 30 days |
| WARNING | Retry, fallback, degradation | 90 days |
| ERROR | Failures, circuit breaker | 1 year |
| CRITICAL | Security events, data loss | Permanent (audit) |

### 9.3 Health Checks

```python
@app.get("/health/live")
async def liveness() -> dict:
    """K8s-style liveness probe. Process is running."""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness() -> dict:
    """K8s-style readiness probe. All dependencies healthy."""
    checks = {
        "database": await check_db_connection(),
        "llm_gateway": await check_llm_reachable(),
        "disk_space": check_disk_space(min_gb=10),
        "memory": check_memory_available(min_gb=2),
    }
    all_healthy = all(c["healthy"] for c in checks.values())
    status = 200 if all_healthy else 503
    return {"status": "ready" if all_healthy else "not_ready", "checks": checks}
```

---

## ARTIFACT 10: Governance & RBAC Architecture

### 10.1 RBAC Permission Matrix

| Permission | Viewer | Reviewer | Approver | Architect | Admin |
|-----------|--------|----------|----------|-----------|-------|
| View dashboard | Yes | Yes | Yes | Yes | Yes |
| View patches | Yes | Yes | Yes | Yes | Yes |
| Comment on patches | No | Yes | Yes | Yes | Yes |
| Request rework | No | Yes | Yes | Yes | Yes |
| Approve/reject (own) | No | No | Yes | Yes | Yes |
| Approve/reject (any) | No | No | No | Yes | Yes |
| Override architecture | No | No | No | Yes | Yes |
| Manage users | No | No | No | No | Yes |
| Manage subsystems | No | No | No | Yes | Yes |
| Export audit log | No | No | No | Yes | Yes |
| Configure LLM | No | No | No | No | Yes |

### 10.2 3-Dimensional Approval Matrix (MVP Simplified)

**Dimension A: Lifecycle Gates**
```
Migration Complete → Validation Passed → Review Passed → Approved
     [Auto]              [Auto]            [Human]       [Human]
```

**Dimension B: Subsystem Review (MVP)**
```
DTS Review → SoundWire Review → Runtime PM Review
  [Human]       [Human]            [Human or Auto]
```

**Dimension C: Quality Checkpoints (Auto)**
```
Correctness → Dependencies → Style → Philosophy
  [Auto]        [Auto]       [Auto]   [Auto]
```

**Cumulative Status Calculation:**
```python
def cumulative_status(dim_a: Status, dim_b: Status, dim_c: Status) -> Status:
    if any(s == Status.REJECTED for s in [dim_a, dim_b, dim_c]):
        return Status.REJECTED
    if any(s == Status.PENDING for s in [dim_a, dim_b, dim_c]):
        return Status.PENDING
    if all(s == Status.APPROVED for s in [dim_a, dim_b, dim_c]):
        return Status.APPROVED
    return Status.IN_PROGRESS
```

### 10.3 Escalation Engine

**12 Escalation Triggers:**

| # | Trigger | Auto-Action | Notification |
|---|---------|-------------|--------------|
| 1 | Confidence < 0.5 | Request human review | Dashboard + email |
| 2 | Regression probability > 0.7 | Block upstream-ready | Dashboard alert |
| 3 | Maintainer sim rejected | Request rework | Dashboard + email |
| 4 | Dependency graph incomplete | Pause migration | Dashboard alert |
| 5 | DTS validation failed | Request human review | Dashboard alert |
| 6 | SoundWire topology uncertain | Request expert review | Email to architect |
| 7 | Architecture inconsistency | Block + escalate | Email to architect |
| 8 | Watchdog timeout (3x) | Escalate to admin | Dashboard + email |
| 9 | No reviewer response (48h) | Escalate to next reviewer | Email |
| 10 | Approval timeout (72h) | Escalate to admin | Email |
| 11 | Repeated rework (3x) | Escalate to architect | Email |
| 12 | LLM cost > 2x budget | Pause + alert admin | Dashboard + email |

### 10.4 Audit Ledger Specification

```sql
-- Immutable audit log
CREATE TABLE audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT NOT NULL,
    target_type TEXT NOT NULL,    -- patch, rule, user, config
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_state TEXT,            -- JSON snapshot
    after_state TEXT,             -- JSON snapshot
    evidence_hash TEXT,           -- SHA256 of evidence
    chain_hash TEXT NOT NULL      -- Hash(prev_chain_hash + this_row)
);

-- Chain hash ensures tamper evidence
-- Previous hash stored in application state
-- Verification: recompute chain and compare
```

**Integrity Verification:**
```python
def verify_chain(db: sqlite3.Connection) -> bool:
    """Verify audit ledger integrity. Returns True if valid."""
    rows = db.execute("SELECT id, chain_hash FROM audit_ledger ORDER BY id").fetchall()
    prev_hash = "0" * 64  # Genesis hash
    for row_id, chain_hash in rows:
        data = db.execute(
            "SELECT timestamp, event_type, user_id, target_id, action FROM audit_ledger WHERE id = ?",
            (row_id,)
        ).fetchone()
        computed = sha256(f"{prev_hash}{row_id}{json.dumps(data)}".encode()).hexdigest()
        if computed != chain_hash:
            return False
        prev_hash = chain_hash
    return True
```
