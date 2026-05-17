# AURA P1 — Watchdog Governance & Circuit Breaker Governance
## Artifacts: 3, 4 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Agent SDK, Orchestrator, Event Bus)

---

## ARTIFACT 3: WATCHDOG GOVERNANCE RULES

### 3.1 Operational Specification

| Parameter | Value | Justification (AOG) |
|-----------|-------|---------------------|
| Heartbeat interval | 30s | Balance: responsive but not noisy (overhead < 0.1%) |
| Missed threshold | 3 heartbeats | 90s grace = reasonable for slow operations |
| SIGTERM wait | 10s | Enough for graceful DB close, not indefinite |
| SIGKILL fallback | After 10s | Guarantees termination (no hung processes) |
| Max restarts per task | 3 | Prevents infinite loops, alerts human |
| Restart backoff | 5s, 15s, 45s | Exponential: fast first retry, slower later |
| Check frequency | 5s | Scan interval: responsive but not CPU-intensive |
| Max watched agents | 50 | Matches P0 max_concurrent_agents |

### 3.2 State Machine

```
                    ┌──────────┐
        ┌──────────►│ REGISTER │◄──────────┐
        │           │ (agent   │            │
        │           │  spawned)│            │
        │           └────┬─────┘            │
        │                │ heartbeat OK     │
        │                ▼                  │
        │           ┌──────────┐            │
        │           │ RUNNING  │────────────┘
        │           │ (normal  │ heartbeat missing
        │           │  ops)    │
        │           └────┬─────┘
        │                │ 3 missed
        │                ▼
        │           ┌──────────┐
        │           │ STOPPING │◄── SIGTERM sent
        │           │ (10s     │
        │           │  grace)  │
        │           └────┬─────┘
        │                │ still alive
        │                ▼
        │           ┌──────────┐
        │           │ KILLING  │◄── SIGKILL sent
        │           │ (force)  │
        │           └────┬─────┘
        │                │ process exit
        │                ▼
        │           ┌──────────┐
        └───────────┤ COMPLETE │──► event to bus, cleanup
                    │ /FAILED  │
                    └──────────┘
```

### 3.3 Governance Rules (Invariant)

| # | Rule | Violation Consequence |
|---|------|----------------------|
| W-01 | Every spawned agent MUST be registered with watchdog within 1s | Agent killed, task re-queued |
| W-02 | Heartbeat messages MUST use canonical JSON schema | Non-parsable → treated as missed heartbeat |
| W-03 | SIGTERM MUST be attempted before SIGKILL | Direct SIGKILL only if SIGTERM handler missing |
| W-04 | Watchdog MUST never crash the orchestrator | All exceptions caught, error logged, continue |
| W-05 | Terminated agent output MUST be preserved | Output dir kept for 24h, then cleaned |
| W-06 | Watchdog MUST publish all lifecycle events | AGENT_TIMEOUT, AGENT_KILLED → event bus |
| W-07 | Watchdog MUST support graceful shutdown | On stop(): terminate all agents with SIGTERM |

### 3.4 Metrics & Observability

| Metric | Type | Purpose |
|--------|------|---------|
| watchdog_agents_registered | gauge | Current watched agents |
| watchdog_timeouts_total | counter | Total timeouts (by agent_type) |
| watchdog_kills_total | counter | Total SIGKILLs (by reason) |
| watchdog_avg_lifetime_seconds | histogram | Agent lifetime distribution |
| watchdog_restart_count | histogram | Restarts per task |

### 3.5 Troubleshooting Guide

```
SYMPTOM: Agents frequently timeout
CAUSES:
  1. Heartbeat interval misconfigured → check agent rules.md
  2. Agent blocked on I/O (LLM call > 90s) → normal for complex tasks
  3. Agent deadlocked → check agent output for last progress message
  4. Watchdog clock drift → check host NTP sync
DEBUG: tail -f data/logs/core.jsonl | jq 'select(.agent_type=="X")'
FIX:   Increase AGENT_TIMEOUT_SECONDS for specific agent type

SYMPTOM: Agent processes left as zombies
CAUSES:
  1. SIGKILL didn't clean up → check process table
  2. Parent process (orchestrator) didn't reap → bug in asyncio
DEBUG: ps aux | grep aura_agents | grep defunct
FIX:   Add process.wait() after kill, or use Popen.wait_for()

SYMPTOM: Watchdog not detecting heartbeats
CAUSES:
  1. stdout buffering → agent must use flush=True
  2. Pipe closed → agent crashed before heartbeat
  3. JSON parse error → check heartbeat schema
DEBUG: Enable agent debug logging
FIX:   Check protocol envelope format
```

---

## ARTIFACT 4: CIRCUIT BREAKER GOVERNANCE

### 4.1 State Machine (Detailed)

```
┌──────────────────────────────────────────────────────────────┐
│                    CIRCUIT BREAKER FSM                        │
│                                                               │
│  CLOSED ──────────────────────────────────────────────┐      │
│   │  Track failures, window = 60s                      │      │
│   │                                                    │      │
│   │  failures >= 3 in 60s                              │      │
│   ▼                                                    │      │
│  OPEN ──(30s cooldown)──► HALF_OPEN                   │      │
│   ▲                       │ Allow 1 probe call         │      │
│   │                       │                            │      │
│   │  probe fails          │  probe succeeds            │      │
│   │                       ▼                            │      │
│   └──────────────────── CLOSED                         │      │
│                          (reset failures)              │      │
│                                                        │      │
│  Invariants:                                           │      │
│  - Per agent type (failure in "learning" ≠ "refactor") │      │
│  - Half-open allows exactly 1 probe at a time          │      │
│  - Success resets to CLOSED immediately                │      │
│  - Open state publishes event to dashboard             │      │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Configuration

| Parameter | Default | Range | When to Change |
|-----------|---------|-------|---------------|
| failure_threshold | 3 | 2-10 | Increase for flaky agents, decrease for critical |
| window_seconds | 60 | 30-300 | Longer window = more tolerant |
| cooldown_seconds | 30 | 10-120 | Shorter = faster recovery, longer = safer |
| half_open_max_calls | 1 | 1-5 | More calls = faster validation, more risk |
| success_to_close | 1 | 1-3 | More = more confidence needed to close |

### 4.3 Governance Rules (Invariant)

| # | Rule | Violation |
|---|------|-----------|
| CB-01 | Circuit breakers are PER agent type | Global breaker would cause cascade |
| CB-02 | Open state REJECTS immediately (no queueing) | Queueing would hide problems |
| CB-03 | Half-open probes are logged as AUDIT events | Every probe decision recorded |
| CB-04 | Circuit breaker state MUST be queryable | Dashboard shows real-time state |
| CB-05 | State transitions publish events | CIRCUIT_BREAKER_STATE → event bus |
| CB-06 | Half-open timeout = fallback to OPEN | If probe hangs > 2x normal execution |
| CB-07 | Admin can MANUALLY reset breaker | POST /admin/circuit-breaker/{type}/reset |

### 4.4 Per-Agent-Type Defaults

```python
# Different agent types have different breaker configs
CIRCUIT_BREAKER_PROFILES = {
    "learning": CircuitBreakerConfig(
        failure_threshold=5,    # Learning is exploratory — more tolerant
        window_seconds=120,
    ),
    "refactor": CircuitBreakerConfig(
        failure_threshold=3,    # Refactor is critical — strict
        window_seconds=60,
    ),
    "validation": CircuitBreakerConfig(
        failure_threshold=2,    # Validation must work — strictest
        window_seconds=30,
    ),
    "default": CircuitBreakerConfig(),
}
```

### 4.5 Metrics

| Metric | Type | Labels |
|--------|------|--------|
| circuit_breaker_state | gauge | agent_type, state (closed/open/half_open) |
| circuit_breaker_failures | counter | agent_type |
| circuit_breaker_transitions | counter | agent_type, from_state, to_state |
| circuit_breaker_rejected | counter | agent_type |

---

## SELF-VALIDATION

| Question | Answer |
|----------|--------|
| Is watchdog overengineered? | **No.** Simple heartbeat + timeout + kill. Uses std Linux signals. |
| Is circuit breaker overengineered? | **No.** 3-state FSM with 5 config parameters. Industry standard pattern. |
| Do these improve operational safety? | **Yes.** Prevent hung agents, cascading failures, resource leaks. |
| Do these preserve determinism? | **Yes.** All state transitions logged, replayable. |
| Are troubleshooting guides actionable? | **Yes.** Symptom → Cause → Debug command → Fix. |
| Are metrics sufficient? | **Yes.** Gauges + counters cover all operational questions. |
