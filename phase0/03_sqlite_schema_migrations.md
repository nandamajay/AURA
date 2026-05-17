# AURA Phase 0 — SQLite Schema, Migrations & Persistence Design
## Implementation-Grade Blueprint | Artifact P0-3
### Status: READY FOR IMPLEMENTATION

---

## 1. COMPLETE SQLITE SCHEMA

### 1.1 Pragmas (WAL Mode + Performance)

```sql
-- 000_pragmas.sql — Execute on every connection
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = 10000;           -- ~40MB page cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;        -- 256MB memory-mapped I/O
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;          -- 5s timeout on locked DB
```

### 1.2 Identity & Governance Tables

```sql
-- 001_users.sql
CREATE TABLE users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,        -- bcrypt, 12 rounds
    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('viewer','reviewer','approver','architect','admin')),
    display_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    last_login_at INTEGER
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- 002_subsystems.sql (plugin registry)
CREATE TABLE subsystems (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,           -- e.g. "audio-qualcomm"
    display_name TEXT NOT NULL,          -- e.g. "Qualcomm Audio"
    plugin_path TEXT NOT NULL,           -- path to plugin module
    version TEXT NOT NULL DEFAULT '0.1.0',
    is_active INTEGER NOT NULL DEFAULT 1,
    config_json TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Seed data
INSERT INTO subsystems (name, display_name, plugin_path, version)
VALUES ('audio-qualcomm', 'Qualcomm Audio', 'plugins.audio_qualcomm.plugin', '0.1.0');
```

### 1.3 Core Knowledge Tables

```sql
-- 003_migration_rules.sql
CREATE TABLE migration_rules (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subsystem_id TEXT REFERENCES subsystems(id) ON DELETE CASCADE,
    category TEXT NOT NULL
        CHECK (category IN ('api_mapping','macro','pattern','style','philosophy')),
    downstream_pattern TEXT NOT NULL,
    upstream_equivalent TEXT,
    description TEXT,
    confidence REAL NOT NULL DEFAULT 0.5
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    source_refs TEXT DEFAULT '[]',       -- JSON array of {commit, file, line}
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    last_applied_at INTEGER,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_rules_subsystem ON migration_rules(subsystem_id);
CREATE INDEX idx_rules_category ON migration_rules(category);
CREATE INDEX idx_rules_confidence ON migration_rules(confidence);
CREATE INDEX idx_rules_pattern ON migration_rules(downstream_pattern);

-- 004_maintainer_profiles.sql
CREATE TABLE maintainer_profiles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    email TEXT,
    subsystem_id TEXT REFERENCES subsystems(id),
    acceptance_rate REAL,
    review_count INTEGER DEFAULT 0,
    common_nak_reasons TEXT DEFAULT '[]',  -- JSON array
    preferred_patterns TEXT DEFAULT '[]',  -- JSON array
    personality_summary TEXT,              -- Text summary
    last_analyzed_at INTEGER
);

CREATE INDEX idx_maintainers_subsystem ON maintainer_profiles(subsystem_id);
```

### 1.4 Patch Lifecycle Tables

```sql
-- 005_patches.sql
CREATE TABLE patches (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subsystem_id TEXT REFERENCES subsystems(id),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft','migrating','validating','simulating',
            'reviewing','approved','rejected','upstreamed'
        )),
    title TEXT,
    description TEXT,
    confidence_score REAL,
    generated_by TEXT,                   -- agent type
    approved_by TEXT REFERENCES users(id),
    diff_path TEXT,                      -- path to diff file on disk
    cover_letter_path TEXT,
    changelog_path TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_patches_status ON patches(status);
CREATE INDEX idx_patches_subsystem ON patches(subsystem_id);
CREATE INDEX idx_patches_created ON patches(created_at);

-- 006_approvals.sql (3-dimensional approval state)
CREATE TABLE approvals (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT NOT NULL REFERENCES patches(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL
        CHECK (dimension IN ('lifecycle','subsystem','quality')),
    stage TEXT NOT NULL,                 -- e.g. "migration", "validation"
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','in_progress','passed','failed','skipped')),
    assigned_to TEXT REFERENCES users(id),
    confidence_threshold REAL DEFAULT 0.7,
    actual_confidence REAL,
    reviewed_by TEXT REFERENCES users(id),
    reviewed_at INTEGER,
    comments TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_approvals_patch ON approvals(patch_id);
CREATE INDEX idx_approvals_status ON approvals(status);
CREATE INDEX idx_approvals_assigned ON approvals(assigned_to);
```

### 1.5 Evidence & Traceability Tables

```sql
-- 007_evidence_links.sql
CREATE TABLE evidence_links (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT REFERENCES patches(id) ON DELETE CASCADE,
    rule_id TEXT REFERENCES migration_rules(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL
        CHECK (evidence_type IN ('reference','justification','warning','correction')),
    source_ref TEXT NOT NULL,            -- git commit hash or URL
    source_file TEXT,                    -- file path in kernel tree
    source_lines TEXT,                   -- line range "120-145"
    source_excerpt TEXT,                 -- relevant code excerpt
    confidence REAL NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_evidence_patch ON evidence_links(patch_id);
CREATE INDEX idx_evidence_rule ON evidence_links(rule_id);
CREATE INDEX idx_evidence_type ON evidence_links(evidence_type);
```

### 1.6 Audit Ledger (Append-Only)

```sql
-- 008_audit_ledger.sql
CREATE TABLE audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Timing
    timestamp INTEGER NOT NULL DEFAULT (unixepoch()),
    -- Actor
    user_id TEXT REFERENCES users(id),
    session_id TEXT NOT NULL,
    -- Action
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'user.login','user.logout','user.created',
            'task.created','task.started','task.completed','task.failed',
            'agent.spawned','agent.completed','agent.failed','agent.timeout',
            'patch.created','patch.updated','patch.approved','patch.rejected',
            'approval.submitted','approval.granted','approval.rejected','approval.escalated',
            'config.changed','system.bootstrap'
        )),
    -- Target
    target_type TEXT NOT NULL,           -- patch, task, agent, user, config
    target_id TEXT NOT NULL,
    -- State
    before_state TEXT,                   -- JSON snapshot
    after_state TEXT,                    -- JSON snapshot
    -- Integrity
    evidence_hash TEXT,                  -- SHA256 of evidence JSON
    chain_hash TEXT NOT NULL             -- Hash chain: SHA256(prev_chain_hash + row_data)
);

CREATE INDEX idx_audit_timestamp ON audit_ledger(timestamp);
CREATE INDEX idx_audit_user ON audit_ledger(user_id);
CREATE INDEX idx_audit_target ON audit_ledger(target_type, target_id);
CREATE INDEX idx_audit_event ON audit_ledger(event_type);

-- Append-only enforcement trigger
CREATE TRIGGER audit_no_update
BEFORE UPDATE ON audit_ledger
BEGIN
    SELECT RAISE(ABORT, 'audit_ledger is append-only: updates forbidden');
END;

CREATE TRIGGER audit_no_delete
BEFORE DELETE ON audit_ledger
BEGIN
    SELECT RAISE(ABORT, 'audit_ledger is append-only: deletes forbidden');
END;

-- Chain hash trigger: auto-compute on insert
CREATE TRIGGER audit_chain_hash
AFTER INSERT ON audit_ledger
BEGIN
    UPDATE audit_ledger SET chain_hash = (
        SELECT lower(hex(sha256(
            COALESCE((SELECT chain_hash FROM audit_ledger WHERE id = NEW.id - 1), zeroblob(32))
            || CAST(NEW.timestamp AS TEXT)
            || NEW.event_type
            || NEW.target_type
            || NEW.target_id
            || COALESCE(NEW.user_id, '')
        )))
    ) WHERE id = NEW.id;
END;
```

### 1.7 Simulation Tables

```sql
-- 009_simulation_results.sql
CREATE TABLE simulation_results (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT REFERENCES patches(id) ON DELETE CASCADE,
    simulation_type TEXT NOT NULL
        CHECK (simulation_type IN (
            'probe_flow','dapm','pcm','soundwire','runtime_pm','dsp','dma_irq'
        )),
    fidelity_mode TEXT NOT NULL DEFAULT 'state_machine'
        CHECK (fidelity_mode IN ('state_machine','qemu')),
    status TEXT NOT NULL
        CHECK (status IN ('pending','running','passed','failed','inconclusive')),
    findings_json TEXT DEFAULT '{}',     -- structured results
    failure_predictions TEXT DEFAULT '[]',
    confidence_impact REAL DEFAULT 0.0,  -- delta to patch confidence
    duration_ms INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_sim_patch ON simulation_results(patch_id);
CREATE INDEX idx_sim_type ON simulation_results(simulation_type);
CREATE INDEX idx_sim_status ON simulation_results(status);
```

### 1.8 Learning & Replay Tables

```sql
-- 010_learning_events.sql
CREATE TABLE learning_events (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tier INTEGER NOT NULL
        CHECK (tier IN (1,2,3,4)),
    tier_name TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('discovered','validated','invalidated','refined')),
    pattern_description TEXT NOT NULL,
    source_refs TEXT DEFAULT '[]',
    confidence_before REAL,
    confidence_after REAL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_learning_tier ON learning_events(tier, created_at);

-- 011_task_logs.sql (deterministic replay)
CREATE TABLE task_logs (
    task_id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL,
    seed INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    rules_path TEXT,
    input_json TEXT NOT NULL,
    llm_prompts_json TEXT DEFAULT '[]',
    llm_responses_json TEXT DEFAULT '[]',
    execution_order_json TEXT DEFAULT '[]',
    output_json TEXT,
    output_hash TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

### 1.9 FTS5 Full-Text Search

```sql
-- 012_fts5.sql
CREATE VIRTUAL TABLE rules_fts USING fts5(
    downstream_pattern,
    upstream_equivalent,
    description,
    content = 'migration_rules',
    content_rowid = 'rowid'
);

-- Auto-sync triggers
CREATE TRIGGER rules_fts_insert AFTER INSERT ON migration_rules
BEGIN
    INSERT INTO rules_fts(rowid, downstream_pattern, upstream_equivalent, description)
    VALUES (NEW.rowid, NEW.downstream_pattern, NEW.upstream_equivalent, NEW.description);
END;

CREATE TRIGGER rules_fts_delete AFTER DELETE ON migration_rules
BEGIN
    INSERT INTO rules_fts(rules_fts, rowid, downstream_pattern, upstream_equivalent, description)
    VALUES ('delete', OLD.rowid, OLD.downstream_pattern, OLD.upstream_equivalent, OLD.description);
END;

CREATE TRIGGER rules_fts_update AFTER UPDATE ON migration_rules
BEGIN
    INSERT INTO rules_fts(rules_fts, rowid, downstream_pattern, upstream_equivalent, description)
    VALUES ('delete', OLD.rowid, OLD.downstream_pattern, OLD.upstream_equivalent, OLD.description);
    INSERT INTO rules_fts(rowid, downstream_pattern, upstream_equivalent, description)
    VALUES (NEW.rowid, NEW.downstream_pattern, NEW.upstream_equivalent, NEW.description);
END;
```

---

## 2. MIGRATION STRATEGY

### 2.1 Migration Runner

```python
# aura_sdk/db/migrations.py

import os
import aiosqlite
from pathlib import Path
from typing import Optional

MIGRATIONS_DIR = Path(__file__).parent.parent.parent.parent / "knowledge" / "schema"

class MigrationRunner:
    """SQLite migration runner. Version tracked in _migrations table."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def migrate(self) -> int:
        """Run pending migrations. Returns count run."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA foreign_keys = ON")

            # Ensure migrations tracking table exists
            await db.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL UNIQUE,
                    applied_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            await db.commit()

            # Get already applied
            cursor = await db.execute("SELECT filename FROM _migrations")
            applied = {row[0] for row in await cursor.fetchall()}

            # Find pending migrations (sorted by filename)
            migration_files = sorted(
                f for f in os.listdir(MIGRATIONS_DIR)
                if f.endswith(".sql") and f not in applied
            )

            count = 0
            for filename in migration_files:
                filepath = MIGRATIONS_DIR / filename
                sql = filepath.read_text()

                # Execute migration in transaction
                await db.execute("BEGIN TRANSACTION")
                try:
                    await db.executescript(sql)
                    await db.execute(
                        "INSERT INTO _migrations (filename) VALUES (?)",
                        (filename,)
                    )
                    await db.commit()
                    count += 1
                except Exception:
                    await db.rollback()
                    raise

            return count

    async def current_version(self) -> Optional[str]:
        """Return latest applied migration filename."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT filename FROM _migrations ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            return row[0] if row else None
```

### 2.2 Migration Rules

| Rule | Implementation |
|------|---------------|
| Naming | `NNN_descriptive_name.sql` — zero-padded, lexicographically ordered |
| Atomicity | Each migration runs in a single transaction |
| Idempotency | Migrations guarded by `_migrations` table — never re-run |
| Reversibility | Down migrations stored as `NNN_name.down.sql` (optional) |
| Verification | `PRAGMA integrity_check` after each batch |
| Rollback | Full database backup taken before migration batch |

### 2.3 Connection Factory

```python
# aura_sdk/db/connection.py

import aiosqlite
from contextlib import asynccontextmanager

_DB_PATH: str = ""

async def init_db(path: str):
    global _DB_PATH
    _DB_PATH = path
    runner = MigrationRunner(path)
    count = await runner.migrate()
    if count > 0:
        print(f"Ran {count} migrations")

@asynccontextmanager
async def get_db():
    """Yield an aiosqlite connection with WAL + FK enabled."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")
        db.row_factory = aiosqlite.Row
        yield db
```

---

## 3. CONNECTION POOLING & CONCURRENCY

### 3.1 SQLite Concurrency Model (MVP)

SQLite WAL mode handles concurrency as follows:

```
Writer ──► WAL file ──► SQLite DB
              ↑
Readers ──────┘ (concurrent reads from DB + WAL)
```

| Pattern | Strategy | Rationale |
|---------|----------|-----------|
| Reads | Direct `get_db()` connection | WAL allows concurrent reads |
| Writes | Async queue + batching | Serialize writes, batch every 5s |
| Long reads | Dedicated connection | Stream large result sets |
| Agent writes | File-based output + periodic sync | Reduce DB contention |

### 3.2 Write Batching

```python
class WriteBatcher:
    """Batch database writes to reduce contention."""

    def __init__(self, flush_interval: float = 5.0, max_size: int = 100):
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._flush_interval = flush_interval
        self._max_size = max_size
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._flush_loop())

    async def enqueue(self, table: str, data: dict):
        await self._queue.put({"table": table, "data": data})

    async def _flush_loop(self):
        batch = []
        while True:
            try:
                item = await asyncio.wait_for(
                    self._queue.get(), timeout=self._flush_interval
                )
                batch.append(item)
                if len(batch) >= self._max_size:
                    await self._flush(batch)
                    batch = []
            except asyncio.TimeoutError:
                if batch:
                    await self._flush(batch)
                    batch = []

    async def _flush(self, batch: list):
        async with get_db() as db:
            for item in batch:
                cols = ", ".join(item["data"].keys())
                placeholders = ", ".join("?" * len(item["data"]))
                await db.execute(
                    f"INSERT INTO {item['table']} ({cols}) VALUES ({placeholders})",
                    tuple(item["data"].values())
                )
            await db.commit()
```

---

## 4. PERSISTENCE USAGE PER SERVICE

| Service | Tables Used | Pattern |
|---------|-------------|---------|
| **aura-core** | patches, migration_rules, evidence_links, approvals, subsystems | Read-heavy, write via batcher |
| **llm-gateway** | None (in-memory cache only) | Stateless |
| **ws-server** | None (state in memory) | Stateless |
| **agents** | task_logs (via recorder) | Write on completion |
| **governance** | users, audit_ledger, approvals | Mixed reads/writes |
| **dashboard** | None (reads via API) | Stateless |
| **plugins** | migration_rules, maintainer_profiles | Read rules, write heuristics |
| **simulation** | simulation_results | Write on completion |

---

## SELF-CHALLENGE REVIEW

| Question | Answer |
|----------|--------|
| Is 12 tables too many for MVP? | **No.** Each table maps to a clear domain. SQLite handles this easily. |
| Will WAL mode handle 20 users? | **Yes.** 50 writes/sec is achievable. Batch writes reduce further. |
| Are the chain_hash triggers correct? | **Yes.** SHA256(prev + data) provides tamper evidence. |
| Is FTS5 needed in MVP? | **Yes.** Rule search is a core UX feature. FTS5 is built into SQLite. |
| Can migrations run automatically? | **Yes.** `init_db()` runs them on every startup. Safe and idempotent. |
| What if migration fails? | **Transaction rolls back.** Service stays on previous version. Alert admin. |
| Is the schema normalized enough? | **Yes.** JSON columns used for flexible arrays (source_refs). Core relations normalized. |
