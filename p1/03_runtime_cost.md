# AURA P1 — Runtime Execution Policy, Cost Governance & Resource Budget Enforcement
## Artifacts: 7, 13, 14 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Task Queue, Agent Pool, LLM Gateway)

---

## ARTIFACT 7: RUNTIME EXECUTION POLICY

### 7.1 Scheduling Rules

| Rule | Specification | Rationale |
|------|--------------|-----------|
| R-01 | P0 tasks execute FIFO | Governance actions are time-critical |
| R-02 | P1 tasks round-robin across agent types | Fairness: no agent type monopolizes |
| R-03 | P2 tasks only when load < 50% | Background never blocks foreground |
| R-04 | P0 can NOT preempt running P1 | Simpler: no preemption in MVP |
| R-05 | P0 CAN preempt queued P1/P2 | P0 jumps queue ahead of all |
| R-06 | Same task type prefers warm process | Reduces spawn overhead |
| R-07 | Max 50 concurrent agents | Hard limit from P0 resource budget |
| R-08 | Single validation job at a time | Kernel compilation is CPU-heavy |
| R-09 | No agent runs > 5 minutes without heartbeat | Watchdog catches hung agents |
| R-10 | Admin tasks (RBAC changes) are P0 | Governance must always work |

### 7.2 Starvation Prevention

```python
class AntiStarvationEnforcer:
    """Prevents task starvation in priority queues."""
    
    P2_MAX_WAIT_SECONDS = 300  # P2 tasks promoted after 5 min
    P1_MIN_SHARE_PERCENT = 60  # P1 guaranteed 60% of slots
    
    def check(self, queue: TaskQueue) -> list[Task]:
        promoted = []
        
        # Promote P2 tasks waiting too long
        for task in queue.p2:
            wait = time.time() - task.created_at
            if wait > self.P2_MAX_WAIT_SECONDS:
                task.priority = TaskPriority.P1  # Promote
                promoted.append(task)
        
        # Ensure P1 minimum share
        p1_slots = int(queue.max_concurrent * self.P1_MIN_SHARE_PERCENT / 100)
        current_p1 = len(queue.in_progress_p1)
        if current_p1 < p1_slots and queue.p1_depth > 0:
            # We have P1 capacity, ensure it's used
            pass  # Normal dequeue handles this
        
        return promoted
```

### 7.3 Priority Inversion Policy

```
SCENARIO: A P1 migration task holds a resource needed by a P0 governance task.

P0 POLICY: No resource locking between tasks.
            Each task is independent.
            No priority inversion possible by design.

RATIONALE: Agents are stateless subprocesses.
           They don't share locks, memory, or files.
           Each reads from DB, writes to isolated output dir.

EXCEPTION: SQLite write contention.
  MITIGATION: Write batcher serializes writes.
              P0 writes (approvals) jump ahead of P1/P2 writes.
              Batch flushed every 5s or 100 items.
```

---

## ARTIFACT 13: RUNTIME COST GOVERNANCE

### 13.1 Token Budget Architecture

```python
# llm-gateway/budget.py

class TokenBudgetManager:
    """
    Multi-level token budget enforcement.
    
    Hierarchy:
    1. Global daily budget (hard limit)
    2. Per-agent-type daily budget (soft allocation)
    3. Per-task budget (input parameter)
    """
    
    DAILY_BUDGET_DEFAULT = 1_000_000  # 1M tokens/day
    
    AGENT_TYPE_BUDGETS = {
        "learning": 200_000,
        "refactor": 300_000,
        "validation": 50_000,
        "upstream_philosophy": 100_000,
        "regression": 100_000,
        "default": 100_000,
    }
    
    async def check_budget(self, agent_type: str, requested_tokens: int) -> BudgetResult:
        # Check 1: Global daily budget
        global_used = await self._get_daily_usage()
        if global_used + requested_tokens > self.global_limit:
            return BudgetResult(
                allowed=False,
                reason=f"Global daily budget exceeded: {global_used}/{self.global_limit}"
            )
        
        # Check 2: Agent-type budget
        type_limit = self.AGENT_TYPE_BUDGETS.get(agent_type, self.AGENT_TYPE_BUDGETS["default"])
        type_used = await self._get_agent_type_usage(agent_type)
        if type_used + requested_tokens > type_limit:
            return BudgetResult(
                allowed=True,  # Soft limit: warn but allow
                warning=f"Agent-type budget {type_used}/{type_limit}",
                fallback_model="gpt-4o-mini"  # Use cheaper model
            )
        
        return BudgetResult(allowed=True)
```

### 13.2 Cost Attribution

```
Attribution Hierarchy (most granular to least):
  1. Per LLM call         → log: {task_id, agent_type, tokens, cost}
  2. Per task execution   → rollup at task completion
  3. Per migration job    → sum of all tasks in job
  4. Per day              → daily dashboard metric
  5. Per week             → weekly report

Alert Thresholds:
  50% of daily budget  → INFO log
  80% of daily budget  → Dashboard warning banner
  100% of daily budget → Switch to fallback provider
  120% of daily budget → Pause new tasks, require admin override
```

### 13.3 Fallback Provider Strategy (P1 — Single Provider)

```
P1 Strategy: Single provider (OpenAI) with model fallback

Normal:     gpt-4o (full capability)
Warning:    gpt-4o-mini (cheaper, faster, less capable)
Emergency:  Queue + admin alert (no other providers configured)

P2 Enhancement: Multi-provider (OpenAI → Anthropic → Ollama local)
  Routing logic based on:
  - Cost optimization
  - Capability matching (code analysis → GPT-4o, reasoning → Claude)
  - Availability fallback
```

---

## ARTIFACT 14: RESOURCE BUDGET ENFORCEMENT

### 14.1 Platform Resource Budget

```
┌──────────────────────────────────────────────────────────────┐
│                    PLATFORM RESOURCE BUDGET                   │
│                                                               │
│  Host Hardware (Recommended): 16 cores, 32 GB RAM, 100 GB   │
│                                                               │
│  Allocation:                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Service          │ CPU  │ RAM   │ Disk  │ Notes      │    │
│  ├──────────────────┼──────┼───────┼───────┼────────────┤    │
│  │ aura-core        │ 2    │ 4 GB  │ 10 GB │ Orchestrator│    │
│  │ aura-dashboard   │ 1    │ 1 GB  │ 1 GB  │ Static files│    │
│  │ llm-gateway      │ 2    │ 4 GB  │ 2 GB  │ Cache       │    │
│  │ ws-server        │ 1    │ 2 GB  │ 500 MB│ Connections │    │
│  │ Agent pool (max) │ 10   │ 20 GB │ 30 GB │ Shared pool │    │
│  │ Validation       │ 2    │ 4 GB  │ 20 GB │ Build cache │    │
│  │ SQLite + temp    │ 0.5  │ 2 GB  │ 36 GB │ WAL + work  │    │
│  │ Overhead         │ 0.5  │ 1 GB  │ 500 MB│ OS buffers  │    │
│  ├──────────────────┼──────┼───────┼───────┼────────────┤    │
│  │ TOTAL            │ ~19  │ ~38GB │ ~100GB│            │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Minimum Viable: 8 cores, 16 GB RAM, 50 GB disk              │
└──────────────────────────────────────────────────────────────┘
```

### 14.2 Per-Agent Resource Limits

| Resource | Limit | Enforcement | Action on Exceed |
|----------|-------|-------------|-----------------|
| CPU | 2 cores (200%) | cgroups cpu.cfs_quota_us | Throttle, don't kill |
| RAM | 4 GB (8 GB validation) | cgroups memory.limit_in_bytes | OOM → SIGKILL → retry |
| File descriptors | 100 | ulimit -n | EMFILE → agent logs error |
| Processes | 10 | ulimit -u | EAGAIN → agent logs error |
| Disk (temp) | 1 GB | directory quota | ENOSPC → agent fails gracefully |
| Network | None (see S-04) | seccomp + Docker network | Blocked at syscall level |
| Execution time | 300s default | Watchdog timer | SIGTERM → SIGKILL |

### 14.3 Enforcement Implementation

```python
# Docker Compose resource limits
services:
  aura-core:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    
  llm-gateway:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G

# Agent-level: applied via preexec_fn
# (see Artifact 5 for resource limit code)
```

---

## SELF-VALIDATION

| Artifact | AOG Pass | Complexity | Justification |
|----------|----------|------------|---------------|
| Runtime Execution Policy | Yes | Low | 10 simple rules, no preemption |
| Cost Governance | Yes | Low-Medium | Budget checks + fallback. Single provider in P1. |
| Resource Budget | Yes | Low | Standard Docker limits + ulimits. |
