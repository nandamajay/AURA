# AURA P1 — Operational Monitoring & Observability Governance
## Artifacts: 11, 12 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Health Router, Event Bus, Structured Logging)

---

## ARTIFACT 11: OPERATIONAL MONITORING PLAYBOOK

### 11.1 Monitoring Philosophy (MVP-Realistic)

```
PRINCIPLE: No external monitoring dependencies in P1.
  - No Prometheus server
  - No Grafana dashboards  
  - No ELK stack
  - No DataDog/NewRelic

INSTEAD: Self-monitoring + simple endpoints
  - /metrics → Prometheus text format (consumable by external if needed later)
  - /health/live → Process alive
  - /health/ready → All dependencies healthy
  - Structured JSON logs → dashboard reads, human readable
  - Event bus → real-time dashboard updates

RATIONALE (AOG):
  - External monitoring adds 3+ containers
  - 20 users don't need enterprise observability
  - Self-monitoring is sufficient for MVP
  - Upgrade path: scrape /metrics into Prometheus later
```

### 11.2 Health Check Procedures

```bash
# DAILY CHECKS (automated via cron or orchestrator timer)
# ──────────────────────────────────────────
# 1. Service health
curl -s http://localhost:8000/health/ready | jq .status
# Expected: "ready"

# 2. Disk space
df -h ./data | tail -1 | awk '{print $4}'  # Free space
# Alert if < 10GB

# 3. Agent pool
# Query: SELECT COUNT(*) FROM patches WHERE status = 'migrating'
# Alert if > 50 (max concurrent)

# 4. LLM budget
curl -s http://localhost:8002/budget | jq .remaining_percent
# Alert if < 20%

# 5. Error rate
grep -c '"level":"error"' data/logs/core.jsonl
# Alert if > 10 errors in last hour

# 6. Queue depth
curl -s http://localhost:8000/api/v1/queue | jq '.p0_depth + .p1_depth + .p2_depth'
# Alert if > 100

# WEEKLY CHECKS (manual)
# ──────────────────────────────────────────
# 1. Backup verification
gunzip -t data/backups/*.db.gz | tail -5

# 2. Audit log integrity
sqlite3 data/aura.db "SELECT COUNT(*) FROM audit_ledger WHERE chain_hash IS NULL"
# Expected: 0

# 3. Plugin validation
# Run PluginValidator on all loaded plugins

# 4. Secret rotation review
# Check age of secrets in Docker

# 5. Resource usage trend
# Review metrics history for growth patterns
```

### 11.3 Alert Matrix

| Condition | Severity | Notification | Auto-Action |
|-----------|----------|-------------|-------------|
| Service not ready | CRITICAL | Dashboard + log | Docker restart |
| Disk < 10GB | CRITICAL | Dashboard + log | Pause new tasks |
| Memory < 2GB | WARNING | Dashboard | None |
| LLM budget < 20% | WARNING | Dashboard | Switch to mini model |
| LLM budget exhausted | CRITICAL | Dashboard + log | Queue new requests |
| Agent timeout > 5/hour | WARNING | Dashboard | None |
| Circuit breaker open | WARNING | Dashboard | Reject requests |
| Cascade failure | CRITICAL | Dashboard + log | Enter degraded mode |
| Queue depth > 100 | WARNING | Dashboard | None |
| DB integrity fail | CRITICAL | Log + alert | Enter degraded mode |
| Unauthorized access | CRITICAL | Audit + alert | Block IP |

### 11.4 Diagnostics Script

```bash
#!/bin/bash
# scripts/health-check.sh

echo "=== AURA System Diagnostics ==="
echo "Generated: $(date)"
echo ""

echo "--- Services ---"
docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Health}}"

echo ""
echo "--- API Health ---"
curl -s http://localhost:8000/health/ready | python -m json.tool 2>/dev/null || echo "UNREACHABLE"

echo ""
echo "--- LLM Gateway ---"
curl -s http://localhost:8002/health 2>/dev/null || echo "UNREACHABLE"

echo ""
echo "--- Metrics ---"
curl -s http://localhost:8000/metrics | grep -E "(agents_total|queue_depth|llm_tokens)" | head -10

echo ""
echo "--- Disk ---"
df -h ./data

echo ""
echo "--- Memory ---"
free -h

echo ""
echo "--- Recent Errors (last hour) ---"
docker compose logs --since=1h --no-log-prefix 2>/dev/null | \
    grep -i "error\|fatal\|exception" | tail -20 || echo "None found"

echo ""
echo "--- Queue Status ---"
curl -s http://localhost:8000/api/v1/queue | python -m json.tool 2>/dev/null

echo ""
echo "--- Circuit Breakers ---"
curl -s http://localhost:8000/api/v1/agents | python -m json.tool 2>/dev/null | \
    grep -A1 circuit_breaker

echo ""
echo "=== Diagnostics Complete ==="
```

---

## ARTIFACT 12: OBSERVABILITY GOVERNANCE RULES

### 12.1 Logging Specification

```python
# Every log line is JSON with these REQUIRED fields:
{
    "timestamp": "2026-01-15T10:30:00.123Z",   # ISO 8601, UTC
    "level": "info",                              # debug|info|warning|error|critical
    "service": "core",                            # Service name
    "logger": "orchestrator.scheduler",           # Module path
    "trace_id": "uuid",                           # Request trace ID
    "message": "Task queued",                     # Human-readable
    "context": {                                   # Structured data
        "task_id": "uuid",
        "agent_type": "learning",
        "priority": 1
    }
}
```

**Log Levels:**
| Level | When to Use | Retention | Example |
|-------|------------|-----------|---------|
| DEBUG | Agent internal logic | 7 days | "Tokenizing input: 1500 tokens" |
| INFO | Task lifecycle, state changes | 30 days | "Task 123 completed successfully" |
| WARNING | Retry, fallback, degradation | 90 days | "Retry 2/3 for task 123 after timeout" |
| ERROR | Failures, circuit breaker | 1 year | "Agent 456 failed with exit code 2" |
| CRITICAL | Security, data loss, corruption | Permanent | "Database integrity check FAILED" |

**Log Rotation:**
```python
# RotatingFileHandler config
maxBytes = 100 * 1024 * 1024  # 100 MB per file
backupCount = 10               # Keep 10 files
# Total: ~1 GB per service
```

### 12.2 Metric Taxonomy

```
# Prometheus-compatible text format at /metrics

# ── Agent Metrics ──
# TYPE aura_agents_total gauge
aura_agents_total{state="running"} 12
aura_agents_total{state="queued"} 5
aura_agents_total{state="completed"} 147

# TYPE aura_agent_completions_total counter
aura_agent_completions_total{agent_type="learning"} 23
aura_agent_completions_total{agent_type="refactor"} 45

# TYPE aura_agent_failures_total counter
aura_agent_failures_total{agent_type="validation",reason="timeout"} 2

# ── Queue Metrics ──
# TYPE aura_task_queue_depth gauge
aura_task_queue_depth{priority="p0"} 0
aura_task_queue_depth{priority="p1"} 8
aura_task_queue_depth{priority="p2"} 15

# ── LLM Metrics ──
# TYPE aura_llm_tokens_total counter
aura_llm_tokens_total{provider="openai"} 154000

# TYPE aura_llm_cost_dollars counter
aura_llm_cost_dollars_total{provider="openai"} 2.45

# ── Simulation Metrics ──
# TYPE aura_simulation_runs_total counter
aura_simulation_runs_total{sim_type="dapm"} 45

# ── Governance Metrics ──
# TYPE aura_governance_decisions_total counter
aura_governance_decisions_total{action="approve"} 12
aura_governance_decisions_total{action="reject"} 3

# ── Circuit Breaker Metrics ──
# TYPE aura_circuit_breaker_state gauge
aura_circuit_breaker_state{agent_type="refactor",state="closed"} 1
aura_circuit_breaker_state{agent_type="learning",state="open"} 1

# ── System Metrics ──
# TYPE aura_disk_free_bytes gauge
aura_disk_free_bytes{mount="/data"} 53687091200

# TYPE aura_memory_available_bytes gauge
aura_memory_available_bytes 2147483648
```

### 12.3 Event Trace Schema

```python
# All events use the canonical EventEnvelope (P0 frozen contract)
# Additional P1 trace requirements:

class TracedEvent(EventEnvelope):
    """Event with distributed tracing context."""
    
    trace_id: str      # Root trace ID (generated at request start)
    span_id: str       # This event's span ID
    parent_id: str     # Parent span ID (empty for root)
    
    # Trace propagation:
    # Dashboard → API call → trace_id generated
    #           → Agent spawn → same trace_id
    #           → LLM call → same trace_id
    #           → DB write → same trace_id
    # All events in same workflow share trace_id
```

### 12.4 Observability Governance Rules

| # | Rule | Rationale |
|---|------|-----------|
| O-01 | Every agent state change produces an event | Complete lifecycle visibility |
| O-02 | Every task produces at least 3 events (created, started, completed) | Track progress |
| O-03 | Every LLM call is logged with token count | Cost attribution |
| O-04 | Every approval action is audit-logged | Compliance |
| O-05 | Every circuit breaker transition is an event | Operational awareness |
| O-06 | Error logs include stack traces | Debuggability |
| O-07 | Metrics use Prometheus naming conventions | Future compatibility |
| O-08 | Log files are rotated and compressed | Disk management |
| O-09 | Logs are structured JSON (not plain text) | Machine parseable |
| O-10 | Health checks run every 30 seconds | Timely failure detection |

---

## SELF-VALIDATION

| Artifact | AOG Pass | Notes |
|----------|----------|-------|
| Monitoring Playbook | Yes | No external deps, self-monitoring only |
| Observability Rules | Yes | 10 simple rules, standard formats |
