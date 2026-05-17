# AURA Phase 0 — Foundation Layer: Master Index
## Implementation-Grade Specification Set | 6 Documents | 25+ Areas
### Status: SPECIFICATION COMPLETE — READY FOR SCAFFOLDING

---

## EXECUTIVE SUMMARY

Phase 0 establishes the complete foundation for the AURA platform. This specification set contains **6 implementation-grade documents** covering **25+ architectural areas**, derived from **10 refinement passes** over **11 source specifications**.

**Every area is specified to implementation level — not architecture level.**

---

## SPECIFICATION MAP

### Document 1: Monorepo, Workspace & Shared SDK
**File:** `01_monorepo_workspace_sdk.md`

| Area | Specified |
|------|-----------|
| Exact monorepo file tree (all directories) | Yes |
| Workspace/package boundaries | Yes |
| aura-sdk internal structure | Yes |
| Shared Pydantic models (event, agent, task) | Yes |
| Agent stdio protocol (envelope, exit codes) | Yes |
| Event bus implementation (in-memory MVP) | Yes |
| Deterministic replay infrastructure | Yes |
| Agent SDK design (BaseAgent ABC) | Yes |
| Agent implementation pattern (LearningAgent) | Yes |
| Makefile commands | Yes |

### Document 2: Services & Docker Topology
**File:** `02_services_docker_topology.md`

| Area | Specified |
|------|-----------|
| Service-by-service breakdown (4 services) | Yes |
| Each: responsibility, API surface, dependencies, startup, failures | Yes |
| Docker Compose topology (production) | Yes |
| Docker Compose override (development) | Yes |
| Dockerfile templates | Yes |
| Service startup order (5 phases) | Yes |
| Network architecture diagram | Yes |
| Resource budget per service | Yes |
| Port mapping & exposure | Yes |
| Volume mounts | Yes |

### Document 3: SQLite Schema & Migrations
**File:** `03_sqlite_schema_migrations.md`

| Area | Specified |
|------|-----------|
| Complete schema (12 tables) | Yes |
| WAL mode + performance pragmas | Yes |
| FTS5 full-text search | Yes |
| Audit ledger (append-only triggers) | Yes |
| Chain hash for integrity | Yes |
| Migration runner (async, idempotent) | Yes |
| Connection factory (aiosqlite) | Yes |
| Write batching strategy | Yes |
| Persistence usage per service | Yes |

### Document 4: Events, WebSocket & Authentication
**File:** `04_events_websocket_auth.md`

| Area | Specified |
|------|-----------|
| Event taxonomy (26 event types) | Yes |
| Event envelope schema (immutable) | Yes |
| Event channel subscriptions | Yes |
| Event bus implementation (async) | Yes |
| Event buffer (ring buffer for replay) | Yes |
| Task queue (3-tier priority) | Yes |
| Retry semantics (per exit code) | Yes |
| Retry executor implementation | Yes |
| WebSocket connection manager | Yes |
| WebSocket endpoint (FastAPI) | Yes |
| SSE fallback endpoint | Yes |
| Dashboard WS client (React hook) | Yes |
| First-run bootstrap wizard | Yes |
| JWT authentication (create/verify) | Yes |
| RBAC enforcer (5 roles, 12 permissions) | Yes |
| Health check framework (live/ready) | Yes |
| Structured JSON logging (structlog) | Yes |
| Prometheus metrics endpoint | Yes |

### Document 5: Watchdog, Circuit Breaker, Testing & CI/CD
**File:** `05_watchdog_circuit_testing_ci.md`

| Area | Specified |
|------|-----------|
| Watchdog specification (parameters) | Yes |
| Watchdog implementation (heartbeat monitoring) | Yes |
| SIGTERM → SIGKILL termination chain | Yes |
| Circuit breaker state machine | Yes |
| Circuit breaker implementation (per-agent-type) | Yes |
| Test pyramid (unit/integration/e2e) | Yes |
| Test organization | Yes |
| Unit test examples (circuit breaker) | Yes |
| Integration test examples (database) | Yes |
| E2E test examples (Playwright) | Yes |
| CI/CD pipeline (GitHub Actions) | Yes |
| Local development workflow | Yes |
| Makefile | Yes |

### Document 6: Plugins, Replay & DevOps
**File:** `06_plugins_replay_devops.md`

| Area | Specified |
|------|-----------|
| Plugin interface (SubsystemPlugin ABC) | Yes |
| Plugin registry (discovery + loading) | Yes |
| Plugin validation | Yes |
| Qualcomm Audio plugin (reference) | Yes |
| Deterministic context (seeded RNG) | Yes |
| Task recorder (LLM conversation logging) | Yes |
| Replay engine (mock LLM client) | Yes |
| Snapshot system (DB + agent outputs) | Yes |
| Bootstrap script (5-minute setup) | Yes |
| Backup script (daily SQLite backup) | Yes |
| Health check script (diagnostics) | Yes |
| Architecture Decision Records | Yes |
| Implementation readiness checklist (30/30) | Yes |

---

## IMPLEMENTATION PRIORITY QUEUE

Order of implementation within Phase 0:

```
Priority 1: Foundation
  1. aura-sdk package (models, protocol, bus, logging, db)
  2. SQLite schema + migration runner
  3. Docker Compose stack
  4. Health check endpoints

Priority 2: Services
  5. llm-gateway service (OpenAI proxy)
  6. ws-server service (WebSocket + SSE)
  7. aura-core service (orchestrator + routers)
  8. aura-dashboard (React shell + routing)

Priority 3: Agents
  9. BaseAgent ABC + CLI protocol
  10. Learning Agent (#2)
  11. Validation Agent (#7)
  12. Refactor Agent (#6)

Priority 4: Operations
  13. Event bus integration
  14. Watchdog manager
  15. Circuit breaker manager
  16. Task scheduler + queue

Priority 5: Governance
  17. JWT authentication
  18. RBAC enforcer
  19. Bootstrap wizard

Priority 6: Polish
  20. Plugin loading (Qualcomm Audio)
  21. Deterministic replay
  22. Testing suite
  23. CI/CD pipeline
  24. Documentation
  25. Monitoring (metrics + logs)
```

---

## TECHNOLOGY DECISIONS (LOCKED)

| Layer | Technology | Decision |
|-------|-----------|----------|
| Backend | Python 3.12 | Locked |
| Framework | FastAPI 0.110 | Locked |
| Frontend | React 18 + TypeScript + Vite | Locked |
| Database | SQLite (WAL mode) | Locked |
| ORM | SQLAlchemy 2.0 + aiosqlite | Locked |
| LLM | OpenAI GPT-4o (single provider MVP) | Locked |
| Container | Docker + Docker Compose | Locked |
| Auth | JWT + bcrypt | Locked |
| Logs | structlog (JSON) | Locked |
| Metrics | Prometheus text format | Locked |
| Tests | pytest + Playwright | Locked |
| CI/CD | GitHub Actions | Locked |

---

## FILES DELIVERED

| # | File | Pages | Areas |
|---|------|-------|-------|
| 1 | `00_PHASE0_MASTER_INDEX.md` | This file | Cross-reference |
| 2 | `01_monorepo_workspace_sdk.md` | ~15 | Monorepo, SDK, Agent SDK |
| 3 | `02_services_docker_topology.md` | ~12 | Services, Docker, Network |
| 4 | `03_sqlite_schema_migrations.md` | ~10 | Schema, Migrations, Persistence |
| 5 | `04_events_websocket_auth.md` | ~14 | Events, WS, Auth, Health, Logs |
| 6 | `05_watchdog_circuit_testing_ci.md` | ~12 | Watchdog, CB, Testing, CI/CD |
| 7 | `06_plugins_replay_devops.md` | ~14 | Plugins, Replay, DevOps, ADRs |

**Total: ~90 pages of implementation-grade specification**

---

## NEXT STEP

Phase 0 is **specified and ready for scaffolding**. The next action is actual code implementation:

1. Create directory structure (`mkdir -p`)
2. Initialize `aura-sdk` package with `pyproject.toml`
3. Implement SQLite schema + migration runner
4. Create Docker Compose stack
5. Start with `llm-gateway` (simplest service)
6. Work up to `aura-core` (most complex)

The specifications contain sufficient code to guide implementation of every component.

---

*AURA Phase 0 Architecture Stabilization*
*25+ areas specified | 6 documents | 30/30 checklist complete*
*Status: READY FOR SCAFFOLDING*
