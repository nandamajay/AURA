# AURA P1 — Security + Sandboxing Policy, Agent Isolation, Secrets & Command Restrictions
## Artifacts: 1, 2, 5, 6, 16 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Monorepo, Agent SDK, Docker Topology)

---

## ARTIFACT 1: SECURITY + SANDBOXING POLICY

### 1.1 Threat Model (MVP-Realistic)

| ID | Threat | Severity | Likelihood | P0 Mitigation | P1 Enhancement |
|----|--------|----------|------------|---------------|----------------|
| T-01 | LLM prompt injection via kernel source | HIGH | MEDIUM | Input sanitization (P0) | Content validation, max token limits (P1) |
| T-02 | Agent escapes sandbox, accesses host | HIGH | LOW | seccomp-bpf (P0) | Resource quotas, read-only FS (P1) |
| T-03 | API key exposure in logs | HIGH | MEDIUM | Keys never in stdout (P0) | Structured log scrubbing (P1) |
| T-04 | Unauthorized patch approval | HIGH | LOW | RBAC (P0) | Audit immutable ledger (P1) |
| T-05 | Kernel source tampering | MEDIUM | LOW | Read-only mounts (P0) | Mount verification on startup (P1) |
| T-06 | Privilege escalation via agent | MEDIUM | LOW | Non-root user (P0) | Capability dropping (P1) |
| T-07 | Session hijacking | MEDIUM | LOW | JWT + httpOnly (P0) | Rate limiting on auth (P1) |
| T-08 | Audit log tampering | MEDIUM | VERY LOW | Append-only (P0) | Chain hash verification (P1) |
| T-09 | LLM cost DoS | MEDIUM | MEDIUM | Token budgets (P0) | Per-task caps, alerts (P1) |
| T-10 | Cross-user data leakage | LOW | LOW | User-scoped queries (P0) | Row-level enforcement (P1) |

**AOG Check: Only 10 threats tracked (not 50+). All have P0 mitigations. P1 adds monitoring, not new infrastructure.**

### 1.2 Security Layers (Defense in Depth)

```
Layer 7: Application    ── RBAC, input validation, audit logging
Layer 6: Session        ── JWT with expiry, httpOnly cookies
Layer 5: Agent          ── Sandbox, resource limits, seccomp-bpf
Layer 4: Container      ── Docker security, non-root user, capability drop
Layer 3: Network        ── Internal Docker network, no external exposure
Layer 2: Host           ── File permissions, volume mounts, resource quotas
Layer 1: Secrets        ── Docker secrets, env var injection, never in code
```

### 1.3 Security Invariants (Never Violate)

| # | Invariant | Enforcement |
|---|-----------|-------------|
| S-01 | Agents NEVER run as root | Docker `USER aura-agent` + uid 1000 |
| S-02 | Kernel sources are read-only | Mount `:ro` + startup verification |
| S-03 | API keys NEVER appear in logs | Log scrubber strips `[A-Za-z0-9_-]{20,}` patterns |
| S-04 | Audit log is append-only | SQLite trigger: `RAISE(ABORT)` on UPDATE/DELETE |
| S-05 | Agent stdout is never executed | Code review + no `eval()`/`exec()` in agent path |
| S-06 | Cross-origin requests blocked | CORS: only dashboard origin allowed |
| S-07 | Auth tokens expire | JWT 24h expiry, sliding refresh max 7 days |
| S-08 | Failed auth is rate-limited | 5 attempts / 15 minutes per IP |
| S-09 | Plugin code is validated before load | `PluginValidator` checks all required methods |
| S-10 | Secrets never committed to git | `.gitignore` + pre-commit hook for `.env` patterns |

### 1.4 Sandboxing Policy

**Every agent process MUST be sandboxed with:**

```python
# aura_agents/sandbox.py

import os
import resource
import subprocess
from dataclasses import dataclass

@dataclass(frozen=True)
class SandboxConfig:
    """Immutable sandbox configuration. Applied on every agent spawn."""
    # User
    uid: int = 1000                    # aura-agent user
    gid: int = 1000
    
    # CPU: 2 cores max
    cpu_quota_percent: int = 200       # 200% = 2 cores (cgroups)
    
    # Memory: 4GB max, no swap
    memory_limit_mb: int = 4096
    memory_swap_mb: int = 4096         # Equal to limit = no swap
    
    # File descriptors
    max_fds: int = 100                 # ulimit -n
    
    # Processes
    max_processes: int = 10            # ulimit -u
    
    # Filesystem
    read_only_mounts: list[str] = None  # ["/kernel-sources", "/rules"]
    writable_mounts: list[str] = None   # ["/data/agents/{task_id}"]
    
    # Network: agents can only reach llm-gateway
    allowed_hosts: list[str] = None     # ["llm-gateway:8000"]
    
    # Time
    max_execution_seconds: int = 300    # Watchdog timeout

SANDBOX_DEFAULTS = SandboxConfig(
    read_only_mounts=["/kernel-sources", "/rules"],
    allowed_hosts=["llm-gateway:8000"],
)

class SandboxEnforcer:
    """Applies sandbox constraints to agent subprocess."""
    
    def apply(self, config: SandboxConfig) -> dict:
        """Return subprocess kwargs with sandbox applied."""
        return {
            "user": config.uid,
            "group": config.gid,
            "env": self._whitelist_env(),
            # Resource limits applied via preexec_fn
        }
    
    def _whitelist_env(self) -> dict:
        """Only pass necessary env vars. Strip all others."""
        allowed = {
            "LLM_GATEWAY_URL",
            "TASK_ID",
            "OUTPUT_DIR",
            "PYTHONPATH",
            "PATH",
            "HOME",
            "LANG",
        }
        return {k: v for k, v in os.environ.items() if k in allowed}
```

### 1.5 seccomp-bpf Policy (Allowed Syscalls)

```python
# Agent processes may ONLY use these syscalls:

ALLOWED_SYSCALLS = frozenset([
    # ── File I/O ──
    "read", "write", "open", "openat", "close",
    "lseek", "pread64", "pwrite64",
    "stat", "fstat", "statfs", "access", "faccessat",
    "getdents", "getdents64", "ioctl",
    "dup", "dup2", "fcntl",
    
    # ── Memory ──
    "mmap", "mprotect", "munmap", "mremap",
    "brk", "sbrk",
    
    # ── Process ──
    "exit", "exit_group", "getpid", "getppid", "getpgrp",
    "getuid", "getgid", "geteuid", "getegid",
    "setuid",  # Required for dropping to aura-agent user
    "setgid",
    "prctl",    # For seccomp itself
    
    # ── Signals ──
    "rt_sigaction", "rt_sigreturn", "rt_sigprocmask",
    "kill", "tkill", "tgkill",
    
    # ── Time ──
    "clock_gettime", "gettimeofday", "time", "nanosleep",
    "clock_nanosleep",
    
    # ── Networking (limited) ──
    "socket",          # AF_INET only
    "connect",         # To allowed_hosts only
    "sendto", "recvfrom",
    "getsockopt", "setsockopt",
    "shutdown", "close",
    
    # ── Threading ──
    "clone", "clone3", "futex", "set_robust_list",
    "getrandom",       # For RNG seeding
    
    # ── Misc ──
    "uname", "sysinfo", "getcwd", "chdir",
    "pipe", "pipe2",
    "poll", "select", "epoll_create", "epoll_ctl", "epoll_wait",
])

DENIED_SYSCALLS = frozenset([
    "execve", "execveat",      # No code execution
    "bind", "listen",           # No incoming connections  
    "accept", "accept4",
    "ptrace",                   # No debugging
    "mount", "umount", "umount2", # No FS changes
    "reboot", "kexec_load",     # No system control
    "iopl", "ioperm",           # No hardware access
    "open_by_handle_at",        # No path traversal
    "perf_event_open",          # No performance monitoring
])
```

---

## ARTIFACT 2: FAILURE RECOVERY PLAYBOOK

### 2.1 Failure Taxonomy

```
┌─────────────────────────────────────────────────────────────┐
│                    FAILURE TAXONOMY                          │
│                                                              │
│  Category          Detection        Auto-Retry    Fallback   │
│  ─────────────────────────────────────────────────────────  │
│  Agent timeout     Watchdog (90s)   Yes (max 3)   Human      │
│  Agent crash       Exit code 1/2    No              Human      │
│  LLM rate limit    HTTP 429         Yes (5x)       Local LLM  │
│  LLM timeout       HTTP timeout     Yes (3x)       Next provider│
│  Validation warn   Exit code 1      No              Human      │
│  Resource OOM      cgroups          Yes (2x)       Reduce load │
│  Disk full         ENOSPC           No              Admin      │
│  Network error     Connection fail  Yes (5x)       Queue      │
│  DB corruption     integrity_check  No              Restore    │
│  Cascade failure   >50% agents fail No              Degraded   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Recovery Procedures (Step-by-Step)

**Procedure F-01: Agent Timeout**
```
TRIGGER:    Watchdog detects 3 missed heartbeats (90s)
DETECTED:   By WatchdogManager._watch_loop() every 5s
ACTION:
  1. Send SIGTERM to agent process
  2. Wait 10s for graceful shutdown
  3. If still alive → SIGKILL
  4. Mark task FAILED_TIMEOUT
  5. Increment retry count
  6. If retry < 3:
       a. Compute backoff: 5s, 15s, 45s
       b. Re-queue task with same priority
  7. If retry >= 3:
       a. Mark TERMINAL_FAILED
       b. Alert dashboard (event: AGENT_FAILED)
       c. Create incident in audit ledger
LOG:        "Agent {id} timed out after {elapsed}s, SIGKILL applied"
AUDIT:      event_type=AGENT_TIMEOUT, target_type=agent, target_id={id}
```

**Procedure F-02: LLM Gateway Failure**
```
TRIGGER:    HTTP error, timeout, or rate limit from OpenAI
DETECTED:   By llm-gateway error handling middleware
ACTION:
  1. Classify error:
     - 429 Rate Limit → retry after Retry-After header
     - 5xx → retry with exponential backoff (1s, 2s, 4s, 8s, 16s)
     - Timeout → retry 3x with 5s backoff
  2. If all retries exhausted:
     a. Return 503 to caller
     b. Caller (agent) receives ExitCode.LLM_UNAVAILABLE
     c. Agent may retry with fallback (see RetryExecutor)
  3. Token budget check:
     a. If daily budget exceeded → queue all new requests
     b. Alert dashboard
LOG:        "LLM request failed: {status}, retries: {count}"
AUDIT:      event_type=LLM_ERROR
```

**Procedure F-03: SQLite Database Recovery**
```
TRIGGER:    PRAGMA integrity_check fails, or corruption detected
DETECTED:   Startup check, or runtime exception on query
ACTION:
  1. Stop accepting new tasks (global circuit breaker)
  2. Alert admin: CRITICAL — database integrity failure
  3. Run: PRAGMA integrity_check → get detailed report
  4. If WAL corruption:
     a. Delete aura.db-wal
     b. Restart — SQLite rebuilds from checkpoint
  5. If DB corruption:
     a. Identify latest backup: ls -t data/backups/ | head -1
     b. Stop aura-core service
     c. Restore: cp backup data/aura.db
     d. Restart aura-core
     e. Re-run migrations
     f. Resume operations
  6. Log full diagnostic bundle
RTO:        5 minutes (from detection to recovery)
RPO:        24 hours (daily backups)
LOG:        "Database recovery: {method}, backup: {file}"
AUDIT:      event_type=SYSTEM_RECOVERY
```

**Procedure F-04: Cascading Failure (Degraded Mode)**
```
TRIGGER:    > 50% of agents failing simultaneously, or global circuit breaker open
DETECTED:   By orchestrator monitoring failure rate
ACTION:
  1. Enter DEGRADED mode:
     a. Stop accepting new migration tasks
     b. Allow governance operations (approvals, audit queries)
     c. Allow read-only dashboard operations
  2. Preserve:
     a. All running agents complete or timeout naturally
     b. Audit log continues recording
     c. Health endpoint returns 503 with degraded=true
  3. Alert:
     a. Dashboard shows "DEGRADED MODE" banner
     b. Admin receives notification
  4. Diagnosis:
     a. Check LLM gateway health
     b. Check disk space
     c. Check memory usage
     d. Review recent error logs
  5. Recovery (manual):
     a. Admin resolves root cause
     b. Admin calls POST /admin/exit-degraded
     c. System resumes normal operation
  6. Post-incident:
     a. Generate incident report from audit log
     b. Update runbooks if needed
LOG:        "DEGRADED mode activated: {reason}"
AUDIT:      event_type=SYSTEM_DEGRADED, after_state={reason}
```

### 2.3 Retry Policy Matrix (P0-P1 Complete)

| Failure | Max Retries | Backoff | Fallback | Human Required |
|---------|------------|---------|----------|----------------|
| Timeout | 3 | 5s, 15s, 45s | Re-queue | After 3 fails |
| LLM rate limit | 5 | 1s, 2s, 4s, 8s, 16s | Local LLM | After 5 fails |
| LLM timeout | 3 | 5s, 15s, 45s | Next provider | After 3 fails |
| Validation error | 0 | N/A | Human review | Yes |
| OOM kill | 2 | 30s, 120s | Reduce parallelism | After 2 fails |
| Disk full | 0 | N/A | Admin cleanup | Yes |
| Network error | 5 | 5s, 15s, 45s, 60s, 60s | Queue | After 5 fails |
| DB error | 3 | 1s, 5s, 15s | Restore | After 3 fails |

---

## ARTIFACT 5: AGENT ISOLATION POLICY

### 5.1 Isolation Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    HOST SYSTEM                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              DOCKER CONTAINER: aura-core                   │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │           PROCESS: orchestrator                      │  │  │
│  │  │                                                      │  │  │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │  │  │
│  │  │  │ Agent: learn │  │ Agent: deps  │  │ Agent: valid │ │  │  │
│  │  │  │ PID: 1001   │  │ PID: 1002   │  │ PID: 1003   │ │  │  │
│  │  │  │ UID: 1000   │  │ UID: 1000   │  │ UID: 1000   │ │  │  │
│  │  │  │ CPU: 2 core │  │ CPU: 2 core │  │ CPU: 2 core │ │  │  │
│  │  │  │ RAM: 4GB    │  │ RAM: 4GB    │  │ RAM: 4GB    │ │  │  │
│  │  │  │ FD: 100     │  │ FD: 100     │  │ FD: 100     │ │  │  │
│  │  │  │ FS: chroot  │  │ FS: chroot  │  │ FS: chroot  │ │  │  │
│  │  │  │ Net: gateway│  │ Net: gateway│  │ Net: gateway│ │  │  │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘ │  │  │
│  │  │                                                      │  │  │
│  │  │  AGENTS CANNOT:                                      │  │  │
│  │  │  - See each other's processes                        │  │  │
│  │  │  - See each other's files                            │  │  │
│  │  │  - Access host filesystem                            │  │  │
│  │  │  - Bind to network ports                             │  │  │
│  │  │  - Execute arbitrary code                            │  │  │
│  │  │  - Escalate privileges                               │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Resource Limits Enforcement

```python
# Applied via preexec_fn in subprocess.Popen()

def apply_resource_limits(config: SandboxConfig):
    """Called in child process before exec."""
    # CPU limit (seconds, not percentage — use cgroups for %)
    resource.setrlimit(resource.RLIMIT_CPU, 
        (config.max_execution_seconds + 10, config.max_execution_seconds + 10))
    
    # Memory limit
    memory_bytes = config.memory_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    
    # File descriptors
    resource.setrlimit(resource.RLIMIT_NOFILE, (config.max_fds, config.max_fds))
    
    # Number of processes
    resource.setrlimit(resource.RLIMIT_NPROC, (config.max_processes, config.max_processes))
    
    # Core dump size (0 = disabled — no core dumps)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    
    # Address space
    resource.setrlimit(resource.RLIMIT_AS, 
        (config.memory_limit_mb * 1024 * 1024, config.memory_limit_mb * 1024 * 1024))
```

### 5.3 Filesystem Restrictions

| Path | Access | Rationale |
|------|--------|-----------|
| `/kernel-sources` | READ-ONLY | Licensing safety, source integrity |
| `/rules` | READ-ONLY | Skill definitions, never modified by agents |
| `/data/agents/{task_id}` | READ-WRITE | Agent output directory (isolated per task) |
| `/tmp` | READ-WRITE | Temporary files, cleaned on exit |
| `/data` (other) | DENIED | No access to DB, logs, exports |
| `/proc` | LIMITED | Only self process info |
| `/sys` | DENIED | No hardware access |
| `/etc` | DENIED | No system config access |
| `/dev` | LIMITED | Only stdin/stdout/stderr/null/random/urandom |
| `/var` | DENIED | No system state access |

---

## ARTIFACT 6: SECRET MANAGEMENT POLICY

### 6.1 Secret Classification

| Tier | Secrets | Storage | Rotation | Access |
|------|---------|---------|----------|--------|
| T1 Critical | OPENAI_API_KEY, JWT_SECRET, DB_ENCRYPTION_KEY | Docker secrets | Manual, quarterly | Single service only |
| T2 Sensitive | ADMIN_PASSWORD (bootstrap), DEV_COMPUTE_SSH_KEY | Env vars (runtime) | On first login / on demand | Bootstrap + specific service |
| T3 Operational | KERNEL_SOURCES_PATH, PLUGIN_PATHS, LOG_LEVEL | Env vars | N/A | All services |

### 6.2 Secret Handling Rules

| Rule | Enforcement |
|------|-------------|
| Never commit secrets | `.gitignore` for `.env`, `*.key`, `secrets/` |
| Never log secrets | Log scrubber: `re.sub(r'sk-[A-Za-z0-9]{20,}', '[REDACTED]', line)` |
| Never echo secrets | Shell commands use `< /run/secrets/...` not command line args |
| Rotate on suspicion | Manual procedure: generate new → update Docker secret → restart |
| Least privilege | Each service gets only the secrets it needs |
| Audit access | All secret access logged (service name, timestamp, secret name) |

### 6.3 Docker Secret Injection (Production)

```yaml
# docker-compose.yml (secret injection)
secrets:
  openai_key:
    file: ./secrets/openai_api_key.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt

services:
  aura-core:
    secrets:
      - openai_key
      - jwt_secret
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_key
      - JWT_SECRET_FILE=/run/secrets/jwt_secret
```

### 6.4 Development Secret Handling

```bash
# .env.example (committed — no real values)
OPENAI_API_KEY=sk-your-key-here
JWT_SECRET=generate-with-openssl-rand-hex-32
ADMIN_PASSWORD=change-after-first-login

# .env (NOT committed — real values)
OPENAI_API_KEY=sk-abc123...
JWT_SECRET=a1b2c3d4...

# scripts/load-secrets.sh (loads into Docker)
docker secret create openai_api_key <(echo "$OPENAI_API_KEY")
```

---

## ARTIFACT 16: COMMAND EXECUTION RESTRICTIONS

### 16.1 Allowed Commands (Agent Whitelist)

Agents may ONLY execute these command categories:

| Category | Allowed Commands | Examples |
|----------|-----------------|----------|
| File operations | `cat`, `head`, `tail`, `grep`, `find`, `diff` | Kernel source analysis |
| Build tools | `make`, `sparse`, `checkpatch.pl` | Validation (S8 wrappers) |
| Git | `git diff`, `git log`, `git show` | Patch analysis |
| Python | `python -m aura_agents.{name}` | Agent execution |
| System | `ps`, `top` (read-only) | Resource monitoring |

### 16.2 Denied Commands (Agent Blacklist)

| Command Category | Reason | Enforcement |
|-----------------|--------|-------------|
| Network tools (`curl`, `wget`, `nc`) | Agents use LLM gateway only | seccomp blocks socket/bind |
| Shell execution (`bash`, `sh`, `zsh`) | No interactive shells | seccomp blocks execve |
| Package managers (`pip`, `apt`, `npm`) | No installation | seccomp + FS restrictions |
| File modification (`rm -rf /`, `dd`) | Read-only mounts | Mount flags + seccomp |
| Privilege escalation (`sudo`, `su`) | Non-root enforced | UID != 0 |
| Code execution (`eval`, `exec`) | No dynamic code | Code review + seccomp |

### 16.3 Validation Agent Exception

The Validation Agent (S8) requires additional permissions:
- `make` with kernel source tree access
- `sparse`, `checkpatch.pl`, `clang`, `dtbs_check`
- Write access to build directory (`/data/tmp/build/`)
- These are granted via a wider sandbox config specific to the validation agent type

```python
VALIDATION_SANDBOX = SandboxConfig(
    memory_limit_mb=8192,    # 8GB for kernel compilation
    cpu_quota_percent=400,    # 4 cores for parallel builds
    writable_mounts=["/data/tmp/build/"],
    max_execution_seconds=1800,  # 30 min for full builds
)
```

---

## SELF-VALIDATION

| Artifact | Complexity | Justified | AOG Pass |
|----------|-----------|-----------|----------|
| Security Policy (T1-T10) | Medium | Yes: all threats real | Yes: no speculative threats |
| Recovery Playbook (F01-F04) | Medium | Yes: covers all P0 failure modes | Yes: no phantom scenarios |
| Agent Isolation | Low-Medium | Yes: required for multi-agent safety | Yes: uses std Linux features |
| Secret Management | Low | Yes: required for API key safety | Yes: standard Docker pattern |
| Command Restrictions | Low | Yes: prevents agent abuse | Yes: deny-list approach |
