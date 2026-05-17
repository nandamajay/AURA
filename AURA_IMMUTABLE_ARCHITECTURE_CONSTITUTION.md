# AURA — Immutable Architecture Constitution
## Cross-Phase Governance Document | P0 + P1 + P2 Unified
### Version: 1.0 | Date: 2026-05-15 | Status: RATIFIED

---

## PREAMBLE

This document is the single source of truth for AURA's architectural governance. It is derived from 11 specification files, refined through 10+ iterative passes, and organized into three implementation phases (P0, P1, P2).

**This Constitution is IMMUTABLE.** Future phases may extend it but may not violate it without formal amendment.

---

## ARTICLE I: SUBSYSTEM ARCHITECTURE

### Section 1.1 — Eight Subsystems (Frozen)

AURA consists of exactly eight subsystems:

| Code | Name | Responsibility | P0 Status | P1 Status | P2 Status |
|------|------|---------------|-----------|-----------|-----------|
| S1 | Orchestrator | Task scheduling, agent lifecycle, circuit breakers | Spec | Spec | Spec |
| S2 | Agent Runtime | 14 CLI executables, process pool, dynamic scaling | Spec | Spec | Spec |
| S3 | Knowledge System | SQLite persistence, 4-tier learning, FTS5 search | Spec | Spec | Spec |
| S4 | Simulation Engine | State-machine simulations, digital twin, hybrid fidelity | Spec | Spec | Spec |
| S5 | Dashboard | React SPA, 12 pages, WebSocket streaming | Spec | Spec | Spec |
| S6 | Governance | 3-pillar: Identity, Approval, Audit | Spec | Spec | Spec |
| S7 | LLM Gateway | Multi-provider routing, token budgets, response cache | Spec | Spec | Spec |
| S8 | Validation Engine | Kernel toolchain: sparse, checkpatch, clang, dtbs_check | Spec | Spec | Spec |

**No additional subsystems may be introduced without amendment to this Constitution.**

### Section 1.2 — Dependency Rules

```
S7 (LLM Gateway) is depended upon by S1, S2
S1 (Orchestrator) depends on S7, S3, S6
S2 (Agents) depends on S7, S8
S5 (Dashboard) depends on S1
S6 (Governance) is queried by S1
S3, S4, S8 have no internal dependencies

RULE: No subsystem may depend on a higher-numbered subsystem.
RULE: S5 (Dashboard) is a read-only consumer of S1.
RULE: S6 (Governance) is read-only for S1 (S1 queries, user actions write).
```

---

## ARTICLE II: CONTRACTS

### Section 2.1 — Agent CLI Contract (Immutable)

Every agent MUST:
- Be an independent CLI executable
- Accept `--task-id`, `--rules`, `--output-dir`, `--llm-gateway` arguments
- Read input via stdin or `--input` file
- Write structured JSON results to stdout
- Send heartbeat JSON to stdout every 30 seconds
- Exit with canonical exit codes (0=success, 1=validation-fail, 2=unrecoverable, 3=timeout, 4=resource, 5=LLM-down)
- Run as non-root user (uid 1000)
- Be subject to resource limits (2 CPU, 4GB RAM, 100 FDs)

### Section 2.2 — Event Envelope Contract (Immutable)

Every event MUST use the canonical EventEnvelope:
- `event_id`: UUID v4
- `event_type`: Enum from EventType (26 types defined)
- `timestamp`: ISO 8601 UTC
- `source`: Subsystem code, service name, agent type, IDs
- `payload`: Typed dictionary
- `trace_id`: UUID for distributed tracing
- `version`: "1.0"

### Section 2.3 — API Contract (Immutable)

All REST endpoints follow `/api/v1/` prefix with:
- GET for reads, POST for creates, PATCH for updates, DELETE for removes
- JSON request/response bodies
- Pydantic-validated schemas
- HTTP status codes: 200 success, 400 bad request, 401 unauthorized, 403 forbidden, 503 degraded

### Section 2.4 — Database Contract (Immutable)

- SQLite with WAL mode
- 12 tables defined in P0 schema
- Append-only audit ledger (UPDATE/DELETE physically prevented)
- Chain hash for tamper evidence
- FTS5 for full-text search
- Migrations are idempotent and version-tracked

---

## ARTICLE III: DETERMINISTIC EXECUTION

### Section 3.1 — Determinism Guarantees

AURA guarantees deterministic execution when:
- Seed is fixed (DeterministicContext)
- Model version is pinned (not "latest")
- Temperature is 0.1 (not > 0.5)
- Execution order is recorded (TaskRecorder)

### Section 3.2 — Replay Requirements

Every task execution MUST be replayable:
- LLM prompts recorded
- LLM responses recorded
- Output hash verified
- 4 fidelity levels: PERFECT, PARTIAL, INCOMPLETE, MISMATCH

### Section 3.3 — Snapshot Requirements

Point-in-time snapshots MUST capture:
- SQLite database + WAL file
- Agent output directories
- Full recoverable state

---

## ARTICLE IV: GOVERNANCE

### Section 4.1 — RBAC (5 Roles)

viewer < reviewer < approver < architect < admin

Permissions defined in P1 RBAC matrix. No role may be added without amendment.

### Section 4.2 — 3-Dimensional Approval

Every patch MUST pass:
- Dimension A: Lifecycle gates (migration → validation → review → approved)
- Dimension B: Subsystem review (DTS → SoundWire → Runtime PM)
- Dimension C: Quality checkpoints (correctness → dependencies → style → philosophy)

### Section 4.3 — Audit Ledger

- Append-only (UPDATE/DELETE physically prevented)
- Chain hash verification available
- Permanent retention
- All user actions, system events recorded

---

## ARTICLE V: ANTI-OVERENGINEERING

### Section 5.1 — Prohibited in P2

| Technology | Status | When |
|-----------|--------|------|
| Kubernetes | PROHIBITED | P4+ only |
| Message queues (Redis/RabbitMQ/NATS) | PROHIBITED | P3+ evaluation |
| Microservices | PROHIBITED | Never (modular monolith) |
| Service mesh (Istio/Linkerd) | PROHIBITED | Never |
| External monitoring (Prometheus/Grafana server) | PROHIBITED | P3+ evaluation |
| External database (PostgreSQL) | PROHIBITED | P3+ evaluation |
| Multiple LLM providers | PROHIBITED | P3+ evaluation |
| Voice/narration implementation | PROHIBITED | P3+ |
| Plugin marketplace | PROHIBITED | P3+ |
| Distributed agent execution | PROHIBITED | P4+ |

### Section 5.2 — Mandatory Patterns

| Pattern | Status |
|---------|--------|
| Modular monolith | MANDATORY |
| Local-first architecture | MANDATORY |
| SQLite WAL | MANDATORY (P2) |
| Docker Compose | MANDATORY (P2) |
| Typed contracts (Pydantic) | MANDATORY |
| Event-driven internals | MANDATORY |
| Explicit APIs | MANDATORY |
| Structured JSON logging | MANDATORY |
| Health checks (live/ready) | MANDATORY |
| Circuit breaker per agent type | MANDATORY |
| Watchdog heartbeat monitoring | MANDATORY |

---

## ARTICLE VI: HUMAN MAINTAINABILITY

### Section 6.1 — Required Documentation

Every subsystem MUST provide:
- Architecture diagram
- Sequence diagram for main workflows
- Failure flow diagram
- Operational playbook
- Troubleshooting guide with debug commands
- Onboarding guide for new engineers

### Section 6.2 — Debuggability Requirements

| Requirement | Implementation |
|-------------|---------------|
| Agent output inspectable | Per-task directory in `./data/agents/` |
| Logs human-readable | Structured JSON, grep-able, jq-friendly |
| Replay available | TaskRecorder enables reproduction without API cost |
| Health checkable | `/health/live` and `/health/ready` endpoints |
| Events observable | WebSocket real-time + event bus logging |
| State queryable | All state in SQLite, queryable via API |

### Section 6.3 — Forbidden Patterns

| Pattern | Status | Reason |
|---------|--------|--------|
| Hidden orchestration | FORBIDDEN | All state transitions must be explicit |
| Implicit state | FORBIDDEN | State must be queryable and logged |
| Magic/auto-configuration | FORBIDDEN | All config must be explicit in .env |
| Deep coupling | FORBIDDEN | Services communicate only via APIs |
| Opaque automation | FORBIDDEN | Every automated action is auditable |

---

## ARTICLE VII: PHASE BOUNDARIES

### Section 7.1 — P0 (Foundation) — SPECIFIED

| Deliverable | Status |
|-------------|--------|
| Monorepo structure | Specified |
| aura-sdk package | Specified |
| Docker Compose stack (4 services) | Specified |
| SQLite schema (12 tables) | Specified |
| Migration runner | Specified |
| Event bus (in-memory) | Specified |
| WebSocket + SSE | Specified |
| JWT authentication | Specified |
| RBAC enforcer | Specified |
| Health checks | Specified |
| Structured logging | Specified |
| Metrics endpoint | Specified |
| Watchdog manager | Specified |
| Circuit breaker | Specified |
| Task scheduler | Specified |
| Retry executor | Specified |
| Plugin registry | Specified |
| Deterministic replay | Specified |
| Bootstrap script | Specified |
| CI/CD pipeline | Specified |

### Section 7.2 — P1 (Operational Governance) — SPECIFIED

| Deliverable | Status |
|-------------|--------|
| Security + Sandboxing Policy | Specified |
| Failure Recovery Playbook (4 procedures) | Specified |
| Watchdog Governance Rules | Specified |
| Circuit Breaker Governance | Specified |
| Agent Isolation Policy | Specified |
| Secret Management Policy | Specified |
| Runtime Execution Policy | Specified |
| Replay Recovery Policy | Specified |
| Backup + Restore Strategy | Specified |
| Disaster Recovery Playbook | Specified |
| Operational Monitoring Playbook | Specified |
| Observability Governance Rules | Specified |
| Runtime Cost Governance | Specified |
| Resource Budget Enforcement | Specified |
| Plugin Trust Model | Specified |
| Command Execution Restrictions | Specified |
| Infrastructure Hardening Checklist (23 items) | Specified |
| Audit + Compliance Retention Rules | Specified |

### Section 7.3 — P2 (Extended Systems) — SPECIFIED

| Deliverable | Status |
|-------------|--------|
| Dashboard UX (12 pages) | Specified |
| Multi-page Navigation | Specified |
| Engineering Workflow UX | Specified |
| Live Agent Visualization | Specified |
| Dependency Graph Visualization (D3.js) | Specified |
| Replay Visualization | Specified |
| Timeline + Audit Visualization | Specified |
| Simulation Visualization (Canvas 2D) | Specified |
| Voice + Narration Architecture | Specified (interface) |
| Interactive Teaching Engine | Specified (interface+basic) |
| Knowledge Graph Visualization (D3.js) | Specified |
| Plugin Marketplace Architecture | Specified (interface) |
| Subsystem Extension Framework | Specified |
| Multi-subsystem Scaling Blueprint | Specified (analysis) |
| Long-term Scalability Evolution Plan | Specified (strategy) |
| K8s Migration Strategy | Specified (strategy) |
| Distributed Execution Strategy | Specified (strategy) |
| Cross-Repository Federation Model | Specified (strategy) |
| AI Model Arbitration Framework | Specified (strategy) |
| Autonomous Learning Evolution | Specified (Tier 1+2) |

---

## ARTICLE VIII: AMENDMENT PROCEDURE

### Section 8.1 — Amendment Requirements

To amend this Constitution:
1. Written proposal with justification
2. Impact analysis on all 8 subsystems
3. AOG assessment (8 questions answered)
4. Cross-phase consistency check
5. Approval by architecture review

### Section 8.2 — Automatic Amendments

The following do NOT require formal amendment:
- New agent types (within S2, using existing BaseAgent)
- New dashboard pages (within S5, using existing components)
- New plugin implementations (using frozen SubsystemPlugin interface)
- New simulation models (using frozen Simulation base class)
- New validation tools (using frozen ValidationTool base class)

---

## SIGNATURE

This Constitution represents the unified architectural agreement for AURA across all three specification phases.

| Phase | Artifacts | Documents | Status |
|-------|-----------|-----------|--------|
| P0 — Foundation | 25 areas | 6 + 1 index | SPECIFIED |
| P1 — Operational Governance | 18 artifacts | 6 + 1 index | SPECIFIED |
| P2 — Extended Systems | 20 artifacts | 6 + 1 index | SPECIFIED |
| **Constitution** | **All phases** | **1** | **RATIFIED** |

**Total: 63+ artifacts across 21 documents. All specified to implementation level.**

---

*AURA Architecture Convergence Complete*
*11 source specifications → 3 phases → 21 documents → 1 Constitution*
