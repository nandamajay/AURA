# AURA Platform — Security, Cost, Failure Recovery, Deterministic Execution & Plugin Architecture
## Artifacts 11-15: Operational Subsystem Specifications
### Version: 1.0 | Stage: Architecture Stabilization | Date: 2026-05-15

---

## ARTIFACT 11: Security Architecture

### 11.1 Threat Model

| Threat ID | Threat | Severity | Mitigation |
|-----------|--------|----------|------------|
| T-01 | LLM prompt injection via kernel source | High | Input sanitization, no exec from LLM output |
| T-02 | Agent escapes sandbox, accesses host | High | seccomp-bpf, non-root user, chroot |
| T-03 | API key exposure in logs | High | Keys never logged, Docker secrets |
| T-04 | Unauthorized patch approval | High | RBAC, multi-dimensional approval |
| T-05 | Kernel source tampering by agents | Medium | Read-only mounts, no write access |
| T-06 | Privilege escalation via agent | Medium | No setuid/setgid, cgroup limits |
| T-07 | Session hijacking | Medium | JWT with expiry, httpOnly cookies, HTTPS |
| T-08 | Audit log tampering | Medium | Append-only, chain hash verification |
| T-09 | LLM cost denial-of-service | Medium | Per-agent token budgets, rate limiting |
| T-10 | Information disclosure between users | Low | User-scoped queries, no cross-user data |

### 11.2 Authentication Flow (Phase 1)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Browser    │────►│  aura-core   │────►│   SQLite     │
│              │     │   /auth      │     │   (users)    │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │
       │── POST /login ────►│
       │   {email, password}│
       │                    │── SELECT * FROM users WHERE email = ?
       │                    │── bcrypt.compare(password, hash)
       │                    │── Generate JWT (exp: 24h)
       │◄── {token} ────────│
       │                    │
       │── GET /dashboard ──►│
       │   Cookie: jwt=...  │── Verify JWT signature
       │                    │── Check expiry
       │◄── Dashboard ──────│
```

**JWT Specification:**
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "reviewer",
  "iat": 1715772000,
  "exp": 1715858400,
  "jti": "unique-token-id"
}
```
- Signing: HS256 with 256-bit secret (Docker secret)
- Expiry: 24 hours
- Refresh: Sliding window (refresh on every request, max 7 days)
- Revocation: Token blacklist in SQLite (for logout/admin action)

### 11.3 Agent Security Profile

```yaml
# Agent security constraints
agent_security:
  user: aura-agent  # uid: 1000, gid: 1000
  groups: [aura-agent]

  capabilities:
    drop: [ALL]
    add: []  # No capabilities

  seccomp:
    mode: filter
    default_action: errno
    allowed_syscalls:  # See Artifact 8 for full list
      - read, write, open, close
      - mmap, mprotect, munmap
      - exit, exit_group
      - clock_gettime
      - socket, connect  # Only to LLM gateway

  filesystem:
    read_only:
      - /kernel-sources
      - /rules
    read_write:
      - /data/agents/{task_id}/
    no_access:
      - /proc
      - /sys
      - /etc/shadow
      - /var/run/docker.sock

  network:
    allowed_hosts:
      - llm-gateway:8000  # Internal only
    blocked_hosts:
      - 0.0.0.0/0

  resources:
    cpu_quota: 200%        # 2 cores
    memory_limit: 4G
    memory_swap: 4G        # No swap
    pids_limit: 10
    file_descriptors: 100
```

### 11.4 Secrets Management

| Secret | Storage | Access | Rotation |
|--------|---------|--------|----------|
| OPENAI_API_KEY | Docker secret / env var | llm-gateway only | Manual |
| ANTHROPIC_API_KEY | Docker secret / env var | llm-gateway only | Manual |
| JWT_SECRET | Docker secret | aura-core only | On demand |
| DB_ENCRYPTION_KEY | Docker secret | aura-core only | On demand |
| DEV_COMPUTE_SSH_KEY | Docker secret | qemu-runner only | On demand |

**Secret Injection Flow:**
```
Host environment → Docker Compose secrets → Container filesystem (/run/secrets/)
→ Application reads at startup → Never logged → Memory only
```

---

## ARTIFACT 12: Cost & Resource Optimization Strategy

### 12.1 LLM Cost Model

| Provider | Model | Input $/1M tokens | Output $/1M tokens | Use Case |
|----------|-------|-------------------|--------------------|----------|
| OpenAI | GPT-4o | $5.00 | $15.00 | Code analysis, refactoring |
| Anthropic | Claude 3.5 Sonnet | $3.00 | $15.00 | Reasoning, maintainer sim |
| Anthropic | Claude 3 Haiku | $0.25 | $1.25 | Quick validation, cheap tasks |
| Local | Ollama (various) | $0.00 | $0.00 | Offline fallback, validation |

### 12.2 Token Budget Architecture

```python
class TokenBudgetManager:
    """Per-agent, per-task, and daily token budget management."""

    DAILY_BUDGETS = {
        "orchestrator": 50_000,
        "learning": 200_000,
        "refactor": 300_000,
        "validation": 50_000,
        "maintainer_reviewer": 150_000,
        "feature_pruning": 100_000,
        "legal_compliance": 50_000,
        # Background agents
        "default": 100_000,
    }

    def check_budget(self, agent_type: str, requested_tokens: int) -> bool:
        daily_used = self.get_daily_usage(agent_type)
        daily_limit = self.DAILY_BUDGETS.get(agent_type, self.DAILY_BUDGETS["default"])
        if daily_used + requested_tokens > daily_limit:
            return False
        return True

    def fallback_chain(self, agent_type: str, task: dict) -> Provider:
        """Select provider based on budget and capability."""
        if self.check_budget(agent_type, task["estimated_tokens"]):
            return self.preferred_provider(agent_type)
        # Budget exceeded → fallback
        if agent_type in ["validation", "legal_compliance"]:
            return Provider.OLLAMA_LOCAL  # Cheap/ free
        return Provider.CLAUDE_HAIKU  # Cheapest remote
```

### 12.3 Cost Attribution Model

```
Per-Task Cost = LLM tokens × provider rate + compute time × instance cost

Attribution Hierarchy:
  1. Per agent execution (granular)
  2. Per migration task (rollup)
  3. Per subsystem (rollup)
  4. Per day (rollup)
  5. Per user (optional)

Cost Alerts:
  - 50% of daily budget → INFO log
  - 80% of daily budget → Dashboard warning
  - 100% of daily budget → Switch to fallback provider
  - 2x daily budget → Pause + admin alert
```

### 12.4 Resource Optimization Strategies

| Strategy | Implementation | Impact |
|----------|---------------|--------|
| Response caching | LRU cache (10K entries) in LLM gateway | 20-40% token reduction |
| Prompt compression | Strip comments, truncate context | 10-20% token reduction |
| Model tiering | Haiku for simple tasks, GPT-4o for complex | 30-50% cost reduction |
| Local fallback | Ollama for validation and cheap tasks | 10-20% cost reduction |
| Batch writes | SQLite batch every 5 seconds | 50% fewer write ops |
| Process pool | Pre-warmed agents reduce spawn time | Faster throughput |
| Compilation cache | Cache kernel build artifacts | 60-80% faster rebuilds |
| Lazy simulation | Only simulate changed components | 50% fewer sim runs |

### 12.5 Monthly Cost Estimate (20 users, moderate usage)

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| OpenAI GPT-4o (~500K tokens/day) | ~$300 |
| Anthropic Claude (~300K tokens/day) | ~$200 |
| Compute (16-core VM) | ~$150 (or existing hardware) |
| Storage (100GB) | ~$10 |
| **Total** | **~$660/month** |

**With optimizations:** ~$400/month (40% reduction)

---

## ARTIFACT 13: Failure Recovery Strategy

### 13.1 Failure Taxonomy

| Category | Examples | Recovery | Auto-Retry |
|----------|----------|----------|------------|
| Agent timeout | Heartbeat missed | Kill + respawn | Yes (max 3) |
| Agent crash | Exit code 1/2 | Log + alert | Code 1: No, Code 2: No |
| LLM error | Rate limit, timeout | Fallback provider | Yes (with backoff) |
| Validation failure | Sparse warnings | Human review required | No |
| Resource exhaustion | OOM, disk full | Scale up or alert | After resource free |
| Dependency failure | LLM gateway down | Queue + retry | Yes (exponential) |
| Data corruption | Invalid SQLite state | Restore from backup | Manual |
| Security event | Sandbox escape attempt | Kill all agents, alert admin | No |

### 13.2 Recovery Procedures

**Procedure 1: Agent Timeout Recovery**
```
1. Watchdog detects 3 missed heartbeats (90s)
2. Send SIGTERM to agent process
3. Wait 10s for graceful shutdown
4. If still alive, SIGKILL
5. Mark task as FAILED_TIMEOUT
6. Check retry count (< 3)
7. If retryable: re-queue with exponential backoff (5s, 15s, 45s)
8. If max retries exceeded: mark TERMINAL_FAILED, alert dashboard
9. Log to audit ledger
```

**Procedure 2: LLM Gateway Failure**
```
1. Detect HTTP error or timeout from LLM gateway
2. Switch to fallback provider (OpenAI → Anthropic → Ollama)
3. If all providers fail: queue task, alert dashboard
4. Retry queue every 60s
5. Auto-recover when any provider responds
6. Log fallback event
```

**Procedure 3: SQLite Corruption**
```
1. Detect integrity check failure (PRAGMA integrity_check)
2. Stop accepting new tasks (circuit breaker)
3. Alert admin immediately
4. Restore from latest backup (./data/backups/)
5. Replay events from WAL file if possible
6. Verify restored database integrity
7. Resume operations
```

**Procedure 4: Cascading Failure**
```
1. Multiple agent types failing simultaneously
2. Circuit breakers open for affected types
3. Global circuit breaker opens if > 50% agents failing
4. Enter degraded mode: governance-only, no new migrations
5. Alert admin with full diagnostic bundle
6. Manual intervention required to exit degraded mode
7. Root cause analysis logged
```

### 13.3 Retry Policy Matrix

| Failure Type | Max Retries | Backoff | Fallback Action |
|-------------|-------------|---------|-----------------|
| Timeout | 3 | 5s, 15s, 45s | Escalate to human |
| LLM rate limit | 5 | 1s, 2s, 4s, 8s, 16s | Switch provider |
| LLM timeout | 3 | 5s, 15s, 45s | Switch provider |
| Validation warning | 0 | N/A | Human review |
| Validation error | 1 | 0s | Human review |
| OOM kill | 2 | 30s, 120s | Reduce parallelism |
| Disk full | 0 | N/A | Admin alert |
| Network error | 5 | 5s, 15s, 45s, 60s, 60s | Queue |

---

## ARTIFACT 14: Deterministic Execution & Replayability Strategy

### 14.1 Determinism Requirements

AURA must produce reproducible results given the same inputs. This is critical for:
- Debugging (same bug should reproduce)
- Audit (prove what happened)
- Testing (deterministic test cases)
- Confidence (results don't change mysteriously)

### 14.2 Sources of Non-Determinism

| Source | Impact | Mitigation |
|--------|--------|------------|
| LLM temperature | Different outputs for same prompt | Fixed temperature (0.1), seed |
| LLM model updates | Newer versions produce different outputs | Pin model versions |
| Concurrency order | Agent execution order affects results | Deterministic scheduling |
| Timing | Time-dependent decisions | Mock time in tests |
| Filesystem order | File listing order | Sort before processing |
| Random sampling | Pattern selection | Fixed random seed |
| Network timing | LLM response timing | Doesn't affect output |

### 14.3 Determinism Controls

```python
class DeterministicContext:
    """Provides deterministic execution environment for agents."""

    def __init__(self, seed: int, model_versions: dict):
        self.seed = seed
        self.rng = random.Random(seed)
        self.model_versions = model_versions
        self.mock_time = None  # For testing

    def llm_params(self) -> dict:
        return {
            "temperature": 0.1,
            "seed": self.seed,
            "model": self.model_versions.get("default", "gpt-4o-2024-08-06"),
        }

    def deterministic_sort(self, items: list) -> list:
        """Sort by deterministic key, not memory address."""
        return sorted(items, key=lambda x: str(x))

    def select_patterns(self, patterns: list, count: int) -> list:
        """Deterministically select patterns using seeded RNG."""
        indices = self.rng.sample(range(len(patterns)), min(count, len(patterns)))
        return [patterns[i] for i in sorted(indices)]
```

### 14.4 Replay Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      REPLAY SYSTEM                               │
│                                                                  │
│   Execution → Task Log (SQLite) → Replay Engine → Same Result   │
│                                                                  │
│   Task Log stores:                                               │
│   - task_id, agent_type, rules_version                           │
│   - input_hash (SHA256 of input data)                            │
│   - seed, model_versions, temperature                            │
│   - llm_prompts (all prompts sent)                               │
│   - llm_responses (all responses received)                       │
│   - execution_order (sequence of operations)                     │
│   - output_hash (SHA256 of result)                               │
│                                                                  │
│   Replay:                                                        │
│   1. Load task log                                               │
│   2. Set same seed, model versions, temperature                  │
│   3. Feed recorded LLM responses (no API calls)                  │
│   4. Execute same operations in same order                       │
│   5. Verify output hash matches                                  │
│                                                                  │
│   Benefits:                                                      │
│   - Debug without API costs                                      │
│   - Regression testing                                           │
│   - Audit verification                                           │
│   - Performance profiling                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 14.5 Snapshot System

```python
class ExecutionSnapshot:
    """Point-in-time snapshot for rollback."""

    def create(self, label: str) -> str:
        snapshot_id = str(uuid4())
        # 1. Save SQLite state (VACUUM INTO)
        # 2. Save agent output directories
        # 3. Save task queue state
        # 4. Record snapshot metadata
        return snapshot_id

    def restore(self, snapshot_id: str) -> None:
        # 1. Stop all agents
        # 2. Restore SQLite from snapshot
        # 3. Restore agent outputs
        # 4. Restore queue state
        # 5. Resume operations
```

---

## ARTIFACT 15: Plugin & Extension Architecture

### 15.1 Plugin Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

@dataclass
class SubsystemContext:
    """Context passed to all plugin methods."""
    subsystem_name: str
    downstream_path: str
    upstream_path: str
    config: dict

class SubsystemPlugin(ABC):
    """Interface for AURA subsystem plugins."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    # Migration
    @abstractmethod
    def get_migration_rules(self, ctx: SubsystemContext) -> list[MigrationRule]: ...

    @abstractmethod
    def analyze_dependencies(self, ctx: SubsystemContext) -> DependencyGraph: ...

    # Validation
    @abstractmethod
    def get_validation_commands(self, ctx: SubsystemContext) -> list[str]: ...

    @abstractmethod
    def parse_validation_output(self, output: str) -> list[ValidationIssue]: ...

    # Maintainer Intelligence
    @abstractmethod
    def get_maintainers(self) -> list[MaintainerProfile]: ...

    @abstractmethod
    def get_review_heuristics(self) -> list[ReviewHeuristic]: ...

    # DTS/Bindings
    @abstractmethod
    def get_dts_conversion_rules(self) -> list[DTSRule]: ...

    @abstractmethod
    def get_binding_schemas(self) -> list[BindingSchema]: ...

    # Simulation
    @abstractmethod
    def get_simulation_models(self) -> list[SimulationModel]: ...

    @abstractmethod
    def get_scenario_tests(self) -> list[ScenarioTest]: ...

    # Dashboard
    @abstractmethod
    def get_dashboard_widgets(self) -> list[DashboardWidget]: ...

    # Explainability
    @abstractmethod
    def get_evidence_types(self) -> list[EvidenceType]: ...
```

### 15.2 Plugin Registration

```python
class PluginRegistry:
    """Discovers and loads subsystem plugins."""

    PLUGIN_PATH = "./plugins/"

    def discover(self) -> dict[str, SubsystemPlugin]:
        """Scan plugin directory for valid plugins."""
        plugins = {}
        for entry in os.scandir(self.PLUGIN_PATH):
            if entry.is_dir() and (entry / "plugin.py").exists():
                plugin = self._load(entry.path)
                plugins[plugin.name] = plugin
        return plugins

    def _load(self, path: str) -> SubsystemPlugin:
        """Dynamic import of plugin module."""
        spec = importlib.util.spec_from_file_location("plugin", f"{path}/plugin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Plugin()  # Plugin class instance
```

### 15.3 Qualcomm Audio Plugin (First Implementation)

```
plugins/audio-qualcomm/
├── plugin.py              # Plugin class implementing SubsystemPlugin
├── rules/
│   ├── api_mappings.json  # Downstream → upstream API mappings
│   ├── macros.json        # Macro conversion rules
│   ├── patterns.json      # Architecture patterns
│   └── anti_patterns.json # Known bad patterns
├── heuristics/
│   ├── dapm_rules.py      # DAPM topology heuristics
│   ├── soundwire_rules.py # SoundWire specific rules
│   └── pm_rules.py        # Runtime PM patterns
├── maintainers/
│   └── audio_maintainers.json  # Known audio subsystem maintainers
├── validation/
│   ├── extra_commands.json     # Additional validation steps
│   └── known_issues.json       # Known false positives
├── dts/
│   ├── binding_schemas/        # DT binding YAML schemas
│   └── conversion_rules.json   # DTS conversion rules
└── tests/
    ├── test_migration.py
    ├── test_validation.py
    └── test_simulation.py
```

### 15.4 Future Plugin Expansion

| Priority | Subsystem | Complexity | Dependencies |
|----------|-----------|------------|-------------|
| P0 | Qualcomm Audio | Baseline | None (defines baseline) |
| P1 | Camera/ISP | Medium | V4L2 patterns |
| P1 | DRM/Display | Medium | DRM subsystem patterns |
| P2 | GPU | High | Complex driver architecture |
| P2 | PCIe | Low | Standard patterns |
| P2 | USB | Low | Standard patterns |
| P3 | WiFi/Bluetooth | High | Firmware complexities |
| P3 | Power Management | Medium | Cross-subsystem |
| P3 | Thermal/Sensors | Low | Simple patterns |

### 15.5 Plugin Validation Framework

```python
class PluginValidator:
    """Validates that a plugin correctly implements the interface."""

    REQUIRED_METHODS = [
        "get_migration_rules",
        "analyze_dependencies",
        "get_validation_commands",
        "parse_validation_output",
        "get_maintainers",
        "get_dts_conversion_rules",
        "get_simulation_models",
        "get_dashboard_widgets",
    ]

    def validate(self, plugin: SubsystemPlugin) -> ValidationResult:
        errors = []
        # Check all required methods
        for method in self.REQUIRED_METHODS:
            if not hasattr(plugin, method):
                errors.append(f"Missing method: {method}")
        # Check return types
        rules = plugin.get_migration_rules(test_context)
        if not all(isinstance(r, MigrationRule) for r in rules):
            errors.append("get_migration_rules must return list[MigrationRule]")
        # Run plugin tests
        test_result = self._run_plugin_tests(plugin)
        return ValidationResult(valid=len(errors) == 0, errors=errors, tests=test_result)
```
