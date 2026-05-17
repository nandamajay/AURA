# AURA Platform — Adversarial Validation & Engineering Memory System

## Document Control

| Property | Value |
|----------|-------|
| Version | 0.1.0 |
| Status | Implemented |
| Date | 2026-05-15 |
| Classification | Architecture Extension — Injections 1 & 2 |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Injection 1: No Fake Success Validation Layer](#2-injection-1-no-fake-success-validation-layer)
3. [Injection 2: Engineering Memory System](#3-injection-2-engineering-memory-system)
4. [Implementation Summary](#4-implementation-summary)
5. [API Endpoints](#5-api-endpoints)
6. [Usage Guide](#6-usage-guide)

---

## 1. Executive Summary

Two critical architectural injections were applied to the AURA platform:

**Injection 1 — Adversarial Validation Framework**: A validation system that never declares success optimistically. It adversarially tests every subsystem through negative testing, chaos testing, replay corruption testing, restart consistency testing, and nondeterminism detection. Reports are truthful, not optimistic.

**Injection 2 — Engineering Memory System**: A persistent context layer with 10 ledgers that records WHY every decision was made. AURA evolves as a traceable engineering system, not a stateless code generator.

Both systems are implemented as first-class platform components, not afterthoughts.

---

## 2. Injection 1: No Fake Success Validation Layer

### 2.1 Philosophy

> **Assume hidden race conditions exist. Assume replay inconsistencies exist. Assume ordering bugs exist. Assume recovery bugs exist. Assume observability gaps exist. Assume audit inconsistencies exist. Assume integration drift exists.**

Do NOT declare anything "stable", "validated", or "production-ready" unless:
- Deterministic replay passes
- Observability is complete
- Failure recovery works
- Audit invariants hold
- Architecture compliance passes
- Reproducibility is verified

### 2.2 Validation Categories (20 test categories)

| Category | Tests | Severity |
|----------|-------|----------|
| NEGATIVE_INPUT | Empty payload, oversized body, malformed JSON, unicode edge cases | Medium |
| NEGATIVE_AUTH | Missing header, expired token, tampered signature | High |
| NEGATIVE_PERMISSIONS | Insufficient role, privilege escalation | High |
| NEGATIVE_DATA | Invalid references, constraint violations | Medium |
| CHAOS_RANDOM_FAILURE | Random 10% request failures | High |
| CHAOS_LATENCY_SPIKE | 2000ms latency injection | Medium |
| CHAOS_RESOURCE_EXHAUSTION | Memory/disk pressure | High |
| CHAOS_NETWORK_PARTITION | Split-brain scenarios | Critical |
| REPLAY_CORRUPTION | Truncated JSON, corrupted hashes | Critical |
| REPLAY_HASH_MISMATCH | Output modified after hash | Critical |
| REPLAY_SNAPSHOT_INTEGRITY | Snapshot corruption recovery | High |
| REPLAY_LLMCALL_REORDERING | LLM call sequence changes | High |
| RESTART_CONSISTENCY | Mid-task container restart | High |
| RESTART_WAL_RECOVERY | WAL replay on crash recovery | High |
| RESTART_MID_TRANSACTION | Transaction rollback verification | Medium |
| DEP_FAILURE_LLMCALL | LLM gateway 502/504 | High |
| DEP_FAILURE_DATABASE | SQLite lock timeout | Medium |
| DEP_FAILURE_WS | WebSocket server down | Medium |
| MALFORMED_EVENT | Missing fields, invalid types | Medium |
| DUPLICATE_EVENT | Duplicate event_id handling | Medium |
| OUT_OF_ORDER_EVENT | Chronological ordering | Medium |
| STALE_TOKEN | Token from deleted user | High |
| PARTIAL_WRITE | Crash mid-transaction | Critical |
| WAL_CONTENTION | Multiple writers conflict | Medium |
| SEED_DRIFT | Different seed than recorded | Medium |
| MODEL_VERSION_DRIFT | Model version mismatch | Medium |
| TIMING_DEPENDENCY | Async scheduling effects | High |

### 2.3 Truthful Reporting

The validation report **never** says:
- "stable"
- "validated"
- "production-ready"
- "all tests passed — system is ready"

It **always** reports:
- How many tests were run
- How many failed
- How many are flaky
- What was skipped
- What needs attention
- Honest recommendation ("Do NOT deploy" when blocking issues exist)

### 2.4 Nondeterminism Detection

**Static analysis** scans code for:
- `random.random()` / `random.choice()` / `random.shuffle()` — unseeded
- `set()` / `dict()` iteration — order-dependent
- `time.time()` / `datetime.now()` — timing-dependent
- `asyncio.gather()` — concurrent execution order
- `hash()` / `id()` — non-deterministic across runs

**Runtime detection** runs functions multiple times and compares outputs. Different outputs across runs = flaky = blocking issue.

**Flaky test detector** runs tests 20 times. Pass rate < 100% = flaky. Pass rate < 50% = likely race condition.

### 2.5 Failure Probability Analysis

Generated per-component:
- Crash probability
- Data loss probability
- Hang probability
- Silent corruption probability
- Cascade probability

Overall risk: UNKNOWN (untested) > LOW > MEDIUM > HIGH

### 2.6 Implementation Files

| File | Purpose |
|------|---------|
| `workspace/aura-sdk/src/aura_sdk/validation/__init__.py` | Package exports |
| `workspace/aura-sdk/src/aura_sdk/validation/models.py` | ValidationPlan, ValidationResult, ValidationReport, EdgeCase, FailureProbability |
| `workspace/aura-sdk/src/aura_sdk/validation/runners.py` | ValidationOrchestrator with 20+ test categories, edge-case matrix generator, failure probability analysis |
| `workspace/aura-sdk/src/aura_sdk/validation/detectors.py` | NondeterminismDetector, FlakyTestDetector, TimingAnalyzer |

---

## 3. Injection 2: Engineering Memory System

### 3.1 Philosophy

> **AURA should evolve as a traceable engineering system, not a stateless code generator.**

Every major implementation decision must record:
- Reasoning
- Tradeoffs
- Rejected alternatives
- Operational implications
- Scalability implications
- Determinism implications
- Observability implications

### 3.2 The 10 Ledgers

| # | Ledger | Purpose | Key Fields |
|---|--------|---------|------------|
| 1 | **Engineering Decision Ledger** | Why decisions were made | reasoning, alternatives, rejected, all implications |
| 2 | **Failure Investigation Ledger** | Root cause analysis | root cause, impact, recovery, prevention, replay implications |
| 3 | **Replay Incident Ledger** | Replay/determinism issues | fidelity, divergence, hash match, LLM call comparison |
| 4 | **Architecture Drift Ledger** | Spec vs. reality | intended vs. actual, compliance impact, remediation |
| 5 | **Operational Incident Ledger** | Production incidents | timeline, response, postmortem, action items |
| 6 | **Stabilization Timeline** | Milestones achieved | changes, tests, stability duration, metrics |
| 7 | **Technical Debt Register** | Known debt | interest rate, current/future impact, payoff, fix effort |
| 8 | **Deferred Scalability Register** | Scalability work deferred | trigger condition, current vs. target, phase estimate |
| 9 | **Known Risk Register** | Known risks | probability, impact, mitigation, contingency, monitoring |
| 10 | **Future Migration Register** | Planned migrations | from/to state, trigger, prerequisites, rollback plan |

### 3.3 Design Principles

- **Append-only**: No UPDATE/DELETE. Status changes only.
- **Every entry has severity**: critical, high, medium, low, info
- **Every entry has status**: open, in_progress, resolved, deferred, wontfix
- **Cross-referenced**: Decisions link to related decisions. Failures link to replay incidents.
- **Queryable**: Full CRUD via REST API for all 10 ledgers
- **Summarizable**: Dashboard shows counts across all ledgers

### 3.4 Pre-Seeded Decisions (Day 1)

Key architectural decisions are pre-recorded:

| Decision | Rationale | Rejected Alternatives |
|----------|-----------|----------------------|
| SQLite over PostgreSQL | Local-first, WAL mode, P2 scale | PostgreSQL (overkill), MySQL (unnecessary complexity) |
| Docker Compose over K8s | P2: single-tenant, team-scale | Kubernetes (18+ months away per Constitution) |
| In-memory event bus | No external deps for P2 | Redis (P3+), RabbitMQ (P3+) |
| CLI agents (never in-process) | Process isolation, deterministic | In-process agents (coupling, memory leaks) |
| Single LLM provider (OpenAI) | P2: simplicity | Multi-provider arbitration (P3+) |
| React + Vite dashboard | Lightweight, fast dev cycle | Next.js (unnecessary), Angular (heavy) |

### 3.5 Pre-Seeded Technical Debt

| Debt | Interest Rate | Current Impact |
|------|--------------|----------------|
| In-memory event bus (no persistence) | Medium | Events lost on restart |
| Single-node SQLite | Medium | No horizontal scaling |
| No circuit breaker implementation | High | LLM failures cascade |
| Basic agent scheduling (no anti-starvation) | Medium | P2 tasks may starve |
| Dashboard pages are stubs (P2 full impl) | Low | Only Command Center functional |

### 3.6 Pre-Seeded Known Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| SQLite corruption under concurrent writes | Low | Critical | WAL mode, busy_timeout, integrity_check |
| LLM API rate limiting | Medium | High | Token budget, caching, retry with backoff |
| Replay nondeterminism | Medium | High | Seeded RNG, pinned models, deterministic sort |
| Plugin sandbox escape | Low | Critical | Restricted execution, seccomp-bpf (P1) |
| Docker container crash mid-task | Low | Medium | Health checks, restart policy |

### 3.7 Implementation Files

| File | Purpose |
|------|---------|
| `workspace/aura-sdk/src/aura_sdk/memory/__init__.py` | Package exports |
| `workspace/aura-sdk/src/aura_sdk/memory/models.py` | 10 Pydantic models for all ledgers |
| `workspace/aura-sdk/src/aura_sdk/memory/persistence.py` | Async CRUD for all 10 ledgers |
| `knowledge/schema/013_memory_tables.sql` | 10 SQLite tables with indexes |
| `services/core/src/core/routers/memory.py` | REST API for all ledgers + validation |

---

## 4. Implementation Summary

### Files Created/Modified

| Category | Files | Description |
|----------|-------|-------------|
| **Validation Models** | 3 Python files | Test categories, plans, results, reports, edge cases, failure probability |
| **Validation Runners** | 1 Python file | Orchestrator, 20+ test categories, edge-case matrix generator |
| **Validation Detectors** | 1 Python file | NondeterminismDetector, FlakyTestDetector, TimingAnalyzer |
| **Memory Models** | 1 Python file | 10 Pydantic models for all ledgers |
| **Memory Persistence** | 1 Python file | Async CRUD for all 10 ledgers with JSON serialization |
| **Memory Schema** | 1 SQL file | 10 SQLite tables (migration 013) |
| **Memory Router** | 1 Python file | 30+ REST endpoints for all ledgers + validation |
| **Core Integration** | 1 Python file | Router registration in main.py |
| **Design Document** | 1 Markdown file | This document |

### New Tables in SQLite

| Table | Rows (empty) | Purpose |
|-------|-------------|---------|
| `engineering_decisions` | 0 | Decision records |
| `failure_investigations` | 0 | Failure analysis |
| `replay_incidents` | 0 | Replay issues |
| `architecture_drift` | 0 | Spec vs. reality |
| `operational_incidents` | 0 | Production incidents |
| `stabilization_timeline` | 0 | Milestones |
| `technical_debt` | 0 | Known debt |
| `deferred_scalability` | 0 | Scalability backlog |
| `known_risks` | 0 | Risk register |
| `future_migrations` | 0 | Migration plans |

### Total New Lines of Code

| Component | Lines |
|-----------|-------|
| Validation framework | ~800 |
| Engineering memory | ~1200 |
| Schema + routers | ~500 |
| **Total** | **~2500** |

---

## 5. API Endpoints

### Validation Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/memory/validation/run` | Run adversarial validation |
| POST | `/api/v1/memory/validation/nondeterminism-check` | Static analysis for nondeterminism |

### Memory Ledger Endpoints (all require auth)

| Method | Path | Ledger | Description |
|--------|------|--------|-------------|
| GET | `/api/v1/memory/summary` | All | Summary counts across all ledgers |
| GET | `/api/v1/memory/decisions` | 1 | List engineering decisions |
| POST | `/api/v1/memory/decisions` | 1 | Record a decision |
| GET | `/api/v1/memory/failures` | 2 | List failure investigations |
| POST | `/api/v1/memory/failures` | 2 | Record a failure |
| GET | `/api/v1/memory/replay-incidents` | 3 | List replay incidents |
| POST | `/api/v1/memory/replay-incidents` | 3 | Record a replay incident |
| GET | `/api/v1/memory/drift` | 4 | List architecture drift |
| POST | `/api/v1/memory/drift` | 4 | Record drift |
| GET | `/api/v1/memory/ops-incidents` | 5 | List operational incidents |
| POST | `/api/v1/memory/ops-incidents` | 5 | Record an ops incident |
| GET | `/api/v1/memory/stabilization` | 6 | List stabilization entries |
| POST | `/api/v1/memory/stabilization` | 6 | Record a milestone |
| GET | `/api/v1/memory/debt` | 7 | List technical debt |
| POST | `/api/v1/memory/debt` | 7 | Record debt |
| GET | `/api/v1/memory/scalability` | 8 | List deferred scalability |
| POST | `/api/v1/memory/scalability` | 8 | Record a deferred item |
| GET | `/api/v1/memory/risks` | 9 | List known risks |
| POST | `/api/v1/memory/risks` | 9 | Record a risk |
| GET | `/api/v1/memory/migrations` | 10 | List future migrations |
| POST | `/api/v1/memory/migrations` | 10 | Record a migration |

---

## 6. Usage Guide

### Running Adversarial Validation

```bash
# Run validation against the core service
curl -X POST http://localhost:8000/api/v1/memory/validation/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "aura-core", "attempts": 5}'

# Check code for nondeterminism
curl -X POST http://localhost:8000/api/v1/memory/validation/nondeterminism-check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_code": "import random\nrandom.random()"}'
```

### Recording Engineering Decisions

```bash
# Record why a decision was made
curl -X POST http://localhost:8000/api/v1/memory/decisions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Event bus: in-memory for P2",
    "subsystem": "S2_AgentRuntime",
    "decision_made": "Use in-memory async pub/sub",
    "reasoning": "No external dependencies for P2. Redis is P3+.",
    "alternatives_considered": [
      {"option": "Redis Streams", "reason_rejected": "Requires Redis deployment; P3+ per Constitution"},
      {"option": "RabbitMQ", "reason_rejected": "Overkill for team-scale; operational complexity"}
    ],
    "scalability_impact": "Limited to single-node; horizontal scaling blocked until P3",
    "reversible": true,
    "reversal_conditions": "When agent count exceeds 50 or multi-node deployment needed"
  }'
```

### Recording Technical Debt

```bash
# Record known debt
curl -X POST http://localhost:8000/api/v1/memory/debt \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "In-memory event bus loses events on restart",
    "subsystem": "S2_AgentRuntime",
    "debt_type": "infrastructure",
    "interest_rate": "medium",
    "current_impact": "Events lost on container restart",
    "future_impact": "Replay impossible for events during restart window",
    "estimated_fix_effort": "3 days",
    "payoff_if_fixed": "Deterministic event recovery, audit completeness"
  }'
```

### Viewing Memory Summary

```bash
# Dashboard summary of all memory
curl http://localhost:8000/api/v1/memory/summary \
  -H "Authorization: Bearer $TOKEN"
```

---

## Appendix A: Constitution Compliance

Both injections comply with the **AURA Immutable Architecture Constitution**:

- **Article I**: Both systems operate within the 8-subsystem architecture (S6 Governance)
- **Article II**: All data contracts use Pydantic models with JSON serialization
- **Article III**: Replay incidents are tracked; nondeterminism is detected
- **Article IV**: Audit ledger records all memory writes; RBAC controls access
- **Article V**: No over-engineering — SQLite storage, no external dependencies
- **Article VI**: All decisions recorded with reasoning for future maintainers
- **Article VII**: Technical debt and deferred scalability map to phase boundaries

---

*End of Document*
