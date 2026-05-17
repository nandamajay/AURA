# AURA Platform — Unified Architecture Document
## Consolidated Analysis of 11 Modular Specification Files
## Version: 1.0 | Date: 2026-05-15 | Stage: Pre-Implementation Analysis

---

# SECTION 1: SPECIFICATION CLASSIFICATION

## 1.1 File-to-Category Mapping

| File | Name | Core Architecture | Orchestration | Governance | Simulation | UX | Agent Systems | Observability | Deployment | Approval Systems | Learning Systems |
|------|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| #3 | AURA Master Orchestration | 60% | — | — | — | 10% | 20% | — | — | — | 10% |
| #4 | Adaptive Agent + Maintainer Intel | — | 25% | — | — | — | 40% | — | — | — | 35% |
| #5 | Platform + Dashboard | 25% | — | — | — | 35% | — | — | — | — | — |
| #6 | Explainability + Scalability | — | — | — | — | — | — | 40% | — | — | 35% |
| #7 | Approval + Escalation + Email | — | — | 35% | — | — | — | 15% | — | 50% | — |
| #8 | Identity + Governance + Audit | — | — | 40% | — | — | — | — | — | — | — |
| #9 | Simulation Sandbox + Digital Twin | — | — | — | 50% | — | — | — | — | — | — |
| #10 | Design-First Execution (META) | — | 50% | — | — | — | — | — | — | — | — |
| #11 | Governance Bootstrap + Lifecycle | — | — | 40% | — | — | — | — | 30% | — | — |
| #12 | Engineering Workflow + UX | — | 35% | — | — | 45% | 20% | — | — | — | — |
| #13 | Feature Pruning + Legal | — | — | 35% | — | — | 35% | — | — | — | 30% |

## 1.2 Category Totals

| Category | Primary Files | Coverage Depth |
|----------|--------------|----------------|
| **Core Architecture** | #3, #5 | 85% — Foundation + Platform |
| **Orchestration** | #10, #12, #4 | 90% — Meta-process + Runtime + Adaptive |
| **Governance** | #8, #11, #7, #13 | 95% — Identity + Lifecycle + Approval + Legal |
| **Simulation** | #9, #5 | 80% — Digital Twin + Architecture Lab |
| **UX** | #12, #5 | 90% — Conversational OS + Dashboard |
| **Agent Systems** | #3, #4, #13, #12 | 95% — 14 agent types defined |
| **Observability** | #6, #9, #7 | 85% — Confidence + Evidence + Simulation |
| **Deployment** | #5, #11 | 60% — Docker + Multi-org (needs clarification) |
| **Approval Systems** | #7, #8 | 90% — Pipeline + RBAC + Audit |
| **Learning Systems** | #3, #4, #6, #13 | 95% — 4-tier learning architecture |

---

# SECTION 2: DEPENDENCY HIERARCHY & IMPLEMENTATION ORDER

## 2.1 Architectural Layers (Bottom-Up)

```
LAYER 0: META-PROCESS FOUNDATION
└─ File #10 — Design-First Execution Philosophy
   ├─ No dependencies (process governor for all)
   └─ Mandates: design-before-code, iterative, CLI agents only

LAYER 1: CORE FOUNDATION
└─ File #3 — AURA Master Orchestration
   ├─ Depends on: File #10 (execution methodology)
   ├─ Provides: 10 core agent types, design principles, learning/execution modes
   └─ Produces: Agent taxonomy, patch generation rules, knowledge persistence model

LAYER 2: PLATFORM INFRASTRUCTURE
├─ File #5 — Docker Platform + Dashboard Foundation
│  ├─ Depends on: File #3 (core design), File #10 (execution)
│  └─ Provides: Containerization, 12-page dashboard spec, shell execution layer
└─ File #11 — Governance Bootstrap + User Lifecycle
   ├─ Depends on: File #5 (platform), File #8 (RBAC defined)
   └─ Provides: First-time wizard, multi-org, user lifecycle

LAYER 3: AGENT INTELLIGENCE
├─ File #4 — Adaptive Agent + Maintainer Intelligence
│  ├─ Depends on: File #3 (base agents), File #10 (CLI mandate)
│  └─ Provides: Dynamic scaling, reviewer agents, self-critique
└─ File #13 — Feature Pruning + Legal Compliance
   ├─ Depends on: File #3 (agent framework), File #4 (review agents)
   └─ Provides: Upstream suitability engine, DCO/SPDX governance

LAYER 4: ORCHESTRATION & INTERACTION
├─ File #12 — Engineering Workflow Interface + UX
│  ├─ Depends on: File #4 (adaptive agents), File #5 (dashboard)
│  └─ Provides: Conversational OS, task graphs, live streaming
└─ File #7 — Approval Workflow + Escalation
   ├─ Depends on: File #8 (RBAC), File #11 (users), File #6 (confidence)
   └─ Provides: 8-stage pipeline, email escalation, reviewer routing

LAYER 5: INTELLIGENCE & OBSERVABILITY
├─ File #6 — Explainability + Scalability + Confidence
│  ├─ Depends on: File #3 (knowledge), File #4 (reviews), File #9 (simulation)
│  └─ Provides: Evidence tracking, confidence scoring, subsystem plugin model
└─ File #9 — Simulation Sandbox + Digital Twin
   ├─ Depends on: File #3 (learning), File #6 (confidence)
   └─ Provides: Runtime simulation, patch impact prediction, scenario testing

LAYER 6: GOVERNANCE & SECURITY
└─ File #8 — Identity + Governance + Audit
   ├─ Depends on: File #5 (platform), File #11 (lifecycle), File #7 (pipeline)
   └─ Provides: 8 auth methods, RBAC, immutable audit ledger
```

## 2.2 Implementation Sequencing (Phase-Aligned)

| Phase | Components | Spec Files | Dependencies |
|-------|-----------|------------|--------------|
| **P0: Design** | Unified architecture document, tech selection | #10 | None |
| **P1: Infrastructure** | Docker platform, database, message queue, CLI agent runtime | #5, #11 | P0 |
| **P2: Core Agents** | 12 agent implementations (CLI executables), orchestrator | #3, #4, #13 | P1 |
| **P3: Intelligence** | Knowledge persistence, learning engine, confidence scoring | #3, #4, #6 | P2 |
| **P4: Simulation** | Digital twin, scenario engine, patch impact prediction | #9 | P3 |
| **P5: Governance** | Auth, RBAC, approval pipeline, audit ledger | #8, #7 | P1 |
| **P6: Dashboard** | 12-page dashboard, real-time streaming, task graphs | #5, #9, #12 | P3, P4, P5 |
| **P7: Integration** | End-to-end workflows, cross-agent testing, load testing | #12, #10 | P2-P6 |

---

# SECTION 3: UNIFIED AGENT ARCHITECTURE (14 Agent Types)

## 3.1 Core Agents (from File #3, reinforced by File #10)

| # | Agent | Responsibility | Execution |
|---|-------|---------------|-----------|
| 1 | Chief Orchestrator | Execution planning, dependency graphs, scheduling, circuit breakers | CLI, singleton |
| 2 | Learning Agent | Discover patterns, compare downstream/upstream, extract rules | CLI, continuous |
| 3 | Driver Dependency Agent | Map includes, APIs, DT deps, firmware, macro relationships | CLI, per-task |
| 4 | DTS/Bindings Agent | DT cleanup, YAML conversion, binding validation | CLI, per-task |
| 5 | Upstream Philosophy Agent | Learn maintainer expectations, analyze LKML reviews | CLI, continuous |
| 6 | Refactor Agent | Downstream-to-upstream transformation, API modernization | CLI, per-task |
| 7 | Validation Agent | sparse, checkpatch, clang, dtbs_check, build testing | CLI, per-patch |
| 8 | Regression Intelligence Agent | Compare output vs upstream refs, detect deviations | CLI, per-patch |
| 9 | Knowledge Base Agent | Persistent learning DB, migration rules, patterns | CLI, persistent |
| 10 | Dashboard Agent | HTML dashboard generation, metrics, visualizations | CLI, persistent |

## 3.2 Extended Agents (from Files #4, #13)

| # | Agent | Responsibility | Source |
|---|-------|---------------|--------|
| 11 | Maintainer Intelligence Reviewer | Simulates maintainer reviews, critiques patches | File #4 |
| 12 | Feature Pruning Agent | Determines upstream suitability, classifies features | File #13 |
| 13 | Legal Compliance Agent | Validates DCO, SPDX, licensing, proprietary boundaries | File #13 |
| 14 | Human Question Agent | Generates targeted architecture clarification questions | File #4 |

## 3.3 Agent Communication Model

```
+-----------------------------------------------------+
|              ORCHESTRATOR (CLI Process)               |
|  - Maintains dependency graph                         |
|  - Schedules agents via stdio                         |
|  - Monitors via watchdog                              |
|  - Circuit breaker per agent                          |
+-----------------------------------------------------+
       |                    |                    |
   stdin/stdout       stdin/stdout          stdin/stdout
       |                    |                    |
  [Agent A]            [Agent B]             [Agent C]
  markdown rules      markdown rules       markdown rules
  isolated memory     isolated memory      isolated memory
  evidence tracking   evidence tracking    evidence tracking
```

**Mandatory Properties (from File #10):**
- Every agent is an independent CLI executable
- Each has dedicated markdown rule files (skillset + memory)
- Each maintains isolated execution context
- Each supports restart/recovery
- Each reports findings via structured stdout
- Each is monitored by watchdog with timeout/circuit breaker

---

# SECTION 4: RESOLVED CONFLICTS & UNIFIED DECISIONS

## 4.1 Conflict Log

| ID | Conflict | Winner | Rationale |
|----|---------|--------|-----------|
| C1 | Agent execution model: File #3 (loose) vs File #10 (strict CLI-only) | **File #10** | Meta-process governs all |
| C2 | Dashboard pages: File #3 (basic), File #5 (9 pages), File #9 (sim pages) | **Merged 12-page model** | See dashboard hierarchy |
| C3 | Approval stages: File #7 (8 stages), File #8 (5 subsys stages), File #4 (7 quality stages) | **3-dimensional matrix** | Lifecycle + Subsystem + Quality |
| C4 | Escalation: File #7 (9 triggers) vs File #8 (7 triggers) | **Unified 12 triggers** | Superset merge |
| C5 | Learning: 4 files with overlapping learning specs | **4-tier architecture** | Tiered by abstraction level |
| C6 | Governance: 3 files scattering governance features | **3 governance pillars** | Identity + Approval + Audit |
| C7 | Chat: File #5 vs File #12 | **File #12 wins** | More comprehensive interaction model |

## 4.2 Key Unified Decisions

1. **CLI Agent Exclusivity**: All 14 agents are standalone CLI executables. No in-process agents.
2. **12-Page Dashboard**: Merged from 3 dashboard specs (see Section 6).
3. **3-Dimensional Approval**: Patches must pass lifecycle gates, subsystem review, AND quality checkpoints.
4. **4-Tier Learning**: Kernel Pattern → Maintainer Intelligence → Cross-Subsystem → Upstream Suitability.
5. **3 Governance Pillars**: Identity & Access + Approval Intelligence + Audit & Compliance.

---

# SECTION 5: DASHBOARD ARCHITECTURE (12 Pages)

## 5.1 Unified Page Hierarchy

| Page | Primary Source | Key Visualizations |
|------|--------------|-------------------|
| 1. Global Command Center | File #5 | System health, active agents, upstream parity, queue depth |
| 2. Driver Migration Center | File #5 | Per-driver status, dependency trees, confidence scores |
| 3. Knowledge Graph Center | File #5 | Subsystem relationships, codec relationships, DAI topology |
| 4. Maintainer Intelligence Center | File #5 | Reviewer profiles, acceptance probability, patch evolution |
| 5. Learning Center | File #5 | Learned rules, extracted patterns, heuristics |
| 6. Live Agent Observability | File #5 | Agent health, CPU/memory, watchdog state, circuit breakers |
| 7. Architecture Lab | File #5 + #9 | Interactive design, DAPM viz, SoundWire simulation |
| 8. Patch Review War Room | File #5 | Inline diffs, maintainer sim comments, style warnings |
| 9. Debugging Center | File #5 + #9 | Logs, traces, IRQ timelines, failure propagation maps |
| 10. Simulation Control Center | File #9 | Active simulations, state machines, probe ordering graphs |
| 11. Approval Operations Center | File #7 | Pending approvals, escalations, reviewer workload |
| 12. Governance Command Center | File #8 | Audit events, role management, security alerts |

---

# SECTION 6: IDENTIFIED GAPS

## 6.1 Critical Gaps Requiring Clarification

| ID | Gap | Impact | Status |
|----|-----|--------|--------|
| G1 | Database schema (SQL vs Graph vs Vector) | HIGH | Needs decision |
| G2 | Inter-agent communication protocol | HIGH | Needs decision |
| G3 | API contracts (REST vs gRPC vs GraphQL) | HIGH | Needs decision |
| G4 | Vector database specification | HIGH | Needs decision |
| G5 | Agent security/sandboxing model | HIGH | Needs decision |
| G6 | Performance/SLA requirements | MEDIUM | Needs decision |
| G7 | Cost/token budget management | MEDIUM | Needs decision |
| G8 | Testing strategy for AURA itself | MEDIUM | Needs decision |
| G9 | Data retention & privacy | MEDIUM | Needs decision |
| G10 | Kernel repository access strategy | HIGH | Needs decision |

---

# SECTION 7: CLARIFICATION QUESTIONS

## 7.1 Questions for User

**Q1 — Deployment Model**: Single-tenant Docker Compose, multi-tenant Kubernetes, or hybrid?

**Q2 — LLM Strategy**: Single provider, multi-provider with routing, local-only, or provider-agnostic?

**Q3 — Persistence Stack**: PostgreSQL+pgvector, Neo4j+Qdrant, SQLite, or pluggable?

**Q4 — Simulation Fidelity**: QEMU-based, behavioral state machines, static analysis, or hybrid?

**Q5 — Governance Priority**: Full enterprise from day one, or minimal auth expanding incrementally?

**Q6 — Dashboard Scale**: Single-user local, team (10-50 users), or enterprise (100+ users)?

**Q7 — Kernel Access**: Read-only mirrors, working copies, sandboxed worktrees, or external mount?

**Q8 — Subsystem Plugin**: Audio-only first with abstraction later, or design plugin system now?

**Q9 — Patch Submission**: Manual handoff, git send-email integration, Patchwork, or PR-based?

**Q10 — Self-Observability**: Platform health monitoring, availability targets, auto-scaling?

---

# APPENDIX A: SPECIFICATION CROSS-REFERENCE MATRIX

| Feature Area | Files Covering It | Primary | Secondary |
|-------------|-------------------|---------|-----------|
| Agent Taxonomy | #3, #4, #10, #12, #13 | #3 | #4, #13 |
| Learning System | #3, #4, #6, #13 | #3 | #4 |
| Dashboard | #3, #5, #7, #8, #9, #12 | #5 | #12 |
| Approval Pipeline | #4, #7, #8 | #7 | #8 |
| Governance | #7, #8, #11, #13 | #8 | #11 |
| Simulation | #5, #9 | #9 | #5 |
| Escalation | #7, #8 | #7 | #8 |
| Chat/Interface | #5, #12 | #12 | #5 |
| Docker/Deploy | #5, #10, #11 | #5 | #11 |
| Knowledge Persistence | #3, #6, #10 | #3 | #6 |
| Confidence Scoring | #4, #6, #9 | #6 | #4 |
| Explainability | #6, #13 | #6 | #13 |

# APPENDIX B: AGENT TYPE SUMMARY

Total Agent Types: 14
- Core (File #3): 10 agents
- Extended (Files #4, #13): 4 agents
- Execution Model: All CLI executables (per File #10 mandate)
- Scaling: Dynamic (per File #4)
- Isolation: Full process isolation with markdown memory

---
*Generated by AURA Architecture Analysis Engine*
*Stage: Pre-Implementation | Awaiting Clarification Responses*
