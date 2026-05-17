# AURA P2 — Long-Term Evolution Strategy: Scalability, K8s, Distributed, Federation, AI Arbitration
## Artifacts: 15, 16, 17, 18, 19 | Anti-Overengineering: CRITICAL — All Strategy, Zero Implementation
### Built on: Frozen P0 + P1

---

## GOVERNANCE PREAMBLE

**This document is PURELY STRATEGIC. It contains ZERO implementation code.**

Every section was challenged with maximum AOG rigor:
- NOTHING here is implemented in P2
- NOTHING here adds containers, services, or dependencies
- These are DECISION RECORDS for future phases
- They exist to PREVENT ad-hoc architecture decisions later

---

## ARTIFACT 15: LONG-TERM SCALABILITY EVOLUTION PLAN

### 15.1 Scaling Triggers (When to Evolve)

| Trigger Metric | Current (P2) | Trigger Value | Action |
|---------------|-------------|---------------|--------|
| Concurrent users | 20 | 50 | Evaluate PostgreSQL |
| Concurrent agents | 50 | 100 | Evaluate agent pool sharding |
| DB writes/second | 10 | 100 | Evaluate write queue |
| Subsystem plugins | 1 | 5 | No action (plugin model handles) |
| LLM requests/min | 200 | 500 | Evaluate multi-provider routing |
| Disk usage (data) | 5 GB | 50 GB | Evaluate cleanup/archive |
| Dashboard latency | <1s | >3s | Evaluate CDN/caching |

### 15.2 Evolution Path (No Implementation)

```
Phase P2 (Now):     SQLite WAL, Docker Compose, single host
                    ↓ [trigger: 50+ users OR 100+ agents]
Phase P3 (Future):  PostgreSQL + pgvector, Docker Compose, single host
                    ↓ [trigger: 100+ users OR 200+ agents]
Phase P4 (Future):  PostgreSQL, Docker Swarm, 2-3 hosts
                    ↓ [trigger: 500+ users OR distributed team]
Phase P5 (Future):  PostgreSQL, Kubernetes, multi-region
                    
NOTE: Each phase is ENTERED only when trigger metrics hit.
      No phase is PREPARED before the trigger.
      This avoids premature optimization.
```

### 15.3 AOG: Is this document justified?

**Yes.** It prevents "we'll figure it out later" decisions that lead to architecture drift. By documenting the trigger conditions, we ensure evolution is data-driven, not speculative.

---

## ARTIFACT 16: FUTURE KUBERNETES MIGRATION STRATEGY

### 16.1 Migration Trigger

**Trigger:** 100+ concurrent users AND multi-region deployment requirement.
**Estimated timeline:** Not before 18 months of operation.

### 16.2 Migration Strategy (Document Only)

```
WHEN TRIGGERED:
  1. Stateless services (dashboard, ws-server) → trivial K8s deployment
  2. aura-core → single Pod with anti-affinity (singleton)
  3. llm-gateway → single Pod (stateless, cache in Redis if needed)
  4. SQLite → migrate to PostgreSQL FIRST (separate step)
  5. Persistent volumes for:
     - /data (PostgreSQL PVC)
     - /rules (ConfigMap)
     - /plugins (init container downloads)
     - /kernel-sources (PVC or NFS)

WHAT CHANGES:
  - docker-compose.yml → Helm chart (template)
  - Service discovery: env vars → K8s DNS
  - Health checks: already compatible (/health/live, /health/ready)
  - Metrics: /metrics endpoint already Prometheus-compatible

WHAT DOES NOT CHANGE:
  - Agent SDK (still CLI subprocesses)
  - Plugin interface (still filesystem-based)
  - Event bus (still in-memory, later Redis)
  - All P0/P1/P2 contracts
```

### 16.3 AOG: Why not start with K8s?

| Question | Answer |
|----------|--------|
| Adds how many components? | 5+ (API server, etcd, kubelet, scheduler, controller) |
| Operational expertise? | Requires K8s operations knowledge |
| Benefit at 20 users? | **Zero.** Docker Compose is simpler and sufficient. |
| Migration cost later? | Low. Stateless services, standard health checks. |
| **Verdict:** | **Do NOT use K8s for P2.** Document strategy only. |

---

## ARTIFACT 17: DISTRIBUTED EXECUTION EVOLUTION STRATEGY

### 17.1 Trigger: Agent Execution on Multiple Hosts

**Trigger:** Agent workloads exceed single-host capacity (50 concurrent agents at limit).
**Estimated timeline:** Not before 12 months.

### 17.2 Strategy (Document Only)

```
APPROACH: Agent Pool Federation (not microservices)

Current (P2):  Orchestrator spawns agents on local host
Future (P4+):  Orchestrator spawns agents on remote hosts

Architecture:
  ┌──────────────┐        SSH/HTTPS          ┌──────────────┐
  │ Orchestrator │◄─────────────────────────►│ Agent Worker │
  │ (main host)  │   Agent spawn request     │ (remote)     │
  │              │   Results + heartbeats    │              │
  └──────────────┘                           └──────────────┘

Changes:
  - AgentPool gains "worker discovery" (SSH config)
  - Agents run on worker hosts, report back via HTTP
  - All P0 agent contracts unchanged (still stdio JSON)
  - Orchestrator still single instance (singleton)

NOT:
  - Not a message queue (RabbitMQ, NATS)
  - Not a service mesh (Istio, Linkerd)
  - Not microservices (agents still ephemeral processes)
  - Just: spawn subprocess over SSH instead of local
```

### 17.3 AOG: Why not distributed now?

| Question | Answer |
|----------|--------|
| Benefit at 20 users/50 agents? | **None.** Single host handles this easily. |
| Complexity added? | High (network failures, worker discovery, split-brain) |
| Debugging harder? | **Yes.** Remote agents are harder to debug. |
| **Verdict:** | **Single host only for P2.** Document strategy for P4+. |

---

## ARTIFACT 18: CROSS-REPOSITORY FEDERATION MODEL

### 18.1 Context: Multiple Kernel Sources

From original spec: AURA needs access to:
- Upstream Linux kernel (public)
- Qualcomm downstream kernel (proprietary)
- LKML archives (public)
- Organization-specific internal kernels (private)

### 18.2 P2 Model: User-Provided Paths

```
P2 (Current):
  User provides KERNEL_SOURCES_PATH env var
  AURA mounts this as read-only volume
  AURA analyzes but NEVER modifies
  
  No federation. No repository management.
  Just: read-only access to git trees.
```

### 18.3 P3+ Strategy: Repository Registry

```
P3+ (Future):
  Repository registry in SQLite:
    
    CREATE TABLE repositories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,           -- "upstream-linux"
        url TEXT,                     -- git URL (optional)
        local_path TEXT NOT NULL,     -- /kernel-sources/upstream/
        type TEXT,                    -- upstream, downstream, internal
        default_branch TEXT,
        last_synced_at INTEGER,
        is_active INTEGER
    );

  Features:
    - Multiple repositories per deployment
    - Repository isolation (upstream vs downstream)
    - Sync tracking (when was LKML last mined)
    - Per-organization repository sets

  NOT:
    - Not a git hosting service (use GitLab/GitHub)
    - Not a code review system (use existing tools)
    - Not a CI system (use existing tools)
```

### 18.4 AOG: Why not repository management in P2?

| Question | Answer |
|----------|--------|
| Current need? | **One kernel source is sufficient for MVP.** |
| Complexity? | Medium (git operations, sync, storage) |
| Benefit? | Low at single-source stage |
| **Verdict:** | **Single path in P2.** Multi-repo in P3+. |

---

## ARTIFACT 19: AI MODEL ARBITRATION FRAMEWORK

### 19.1 P2: Single Provider (OpenAI)

```
P2 Architecture:
  Dashboard → LLM Gateway → OpenAI API
                           (gpt-4o)

No arbitration needed. Single provider.
```

### 19.2 P3+ Strategy: Multi-Provider Arbitration

```
P3+ Architecture:
  Dashboard → LLM Gateway → Router → OpenAI (gpt-4o)
                                   → Anthropic (claude-3.5-sonnet)
                                   → Ollama (local models)

Routing Logic (document only — P3+ implementation):
  1. Cost check: If budget > 80%, route to cheapest provider
  2. Capability check: Code analysis → GPT-4o, Reasoning → Claude
  3. Availability check: If provider down, route to next
  4. Latency check: If queue depth > 10, route to fastest
  5. Fallback: All fail → queue + admin alert

Provider Configuration:
  providers:
    openai:
      model: gpt-4o
      priority: 1
      cost_per_1k: $0.005
    anthropic:
      model: claude-3-sonnet
      priority: 2
      cost_per_1k: $0.003
    ollama:
      model: llama3:70b
      priority: 3
      cost_per_1k: $0  # Local
      requires: gpu    # Needs GPU host
```

### 19.3 AOG: Why not multi-provider in P2?

| Question | Answer |
|----------|--------|
| Benefit at 20 users? | **Low.** Single provider handles load. |
| Cost savings? | Marginal at low volume. |
| Complexity? | Medium (routing logic, error handling, cost tracking) |
| **Verdict:** | **Single provider in P2.** Document multi-provider for P3+. |

---

## SELF-VALIDATION: ALL 5 STRATEGY ARTIFACTS

| Artifact | Type | Implementation | AOG Pass | Justification |
|----------|------|---------------|----------|---------------|
| Long-term Scalability | Trigger-based plan | None | Yes | Prevents premature optimization |
| K8s Migration | Migration strategy | None | Yes | Documented but NOT started |
| Distributed Execution | SSH-based agents | None | Yes | Simplest possible distribution |
| Cross-Repository Federation | Registry schema | None | Yes | P3+ when multi-source needed |
| AI Model Arbitration | Router interface | None | Yes | P3+ when cost optimization needed |

**ALL 5 artifacts are PURE STRATEGY. ZERO code. ZERO new infrastructure. ZERO new dependencies.**

This is the correct application of the Anti-Overengineering Governor.

---

## P2 COMPLETE ARTIFACT SUMMARY

| # | Artifact | File | P2 Status |
|---|----------|------|-----------|
| 1 | Dashboard UX Spec | `01_dashboard_ux.md` | Full spec |
| 2 | Multi-page Navigation | `01_dashboard_ux.md` | Full spec |
| 3 | Engineering Workflow UX | `01_dashboard_ux.md` | Full spec |
| 4 | Live Agent Visualization | `02_visualization_systems.md` | Full spec |
| 5 | Dependency Graph Viz | `02_visualization_systems.md` | Full spec |
| 6 | Replay Visualization | `02_visualization_systems.md` | Full spec |
| 7 | Timeline + Audit Viz | `02_visualization_systems.md` | Full spec |
| 8 | Simulation Viz Engine | `02_visualization_systems.md` | Full spec |
| 9 | Voice + Narration | `03_voice_teaching_learning.md` | Interface only |
| 10 | Interactive Teaching | `03_voice_teaching_learning.md` | Interface + basic |
| 11 | Knowledge Graph Viz | `02_visualization_systems.md` | Full spec |
| 12 | Plugin Marketplace | `04_plugin_marketplace.md` | Interface only |
| 13 | Subsystem Extension | `04_plugin_marketplace.md` | Full spec |
| 14 | Multi-subsystem Scaling | `04_plugin_marketplace.md` | Analysis |
| 15 | Long-term Scalability | `05_evolution_strategy.md` | Strategy |
| 16 | K8s Migration | `05_evolution_strategy.md` | Strategy |
| 17 | Distributed Execution | `05_evolution_strategy.md` | Strategy |
| 18 | Cross-Repository Federation | `05_evolution_strategy.md` | Strategy |
| 19 | AI Model Arbitration | `05_evolution_strategy.md` | Strategy |
| 20 | Autonomous Learning | `03_voice_teaching_learning.md` | Tier 1+2 |

**P2: 20/20 artifacts complete.**
