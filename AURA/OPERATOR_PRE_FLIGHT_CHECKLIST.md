# AURA Operator Pre-Flight Checklist
## What to Keep in Mind Before Your CLI Agent Starts Executing

---

## 1. Your Environment Must Be Ready First

Before the agent does anything, verify these on your host machine:

```bash
# Required versions
python3 --version      # MUST be 3.12+
docker --version       # MUST be 24.0+
docker compose version # MUST be v2.20+
pip --version          # Should be 23.0+
```

**If Python < 3.12**: The code uses `datetime.UTC` aliases, `StrEnum`, and type parameter syntax (`list[T]`) that require 3.12. Upgrade before starting.

**If Docker is not running**: Phase F (Docker Compose) will fail. Start Docker Desktop or the daemon before the agent reaches that phase.

**No `docker compose` subcommand?** Some systems still use `docker-compose` (hyphen). The Makefile uses `docker compose` (space). If your system uses the hyphen, either upgrade Docker or alias it.

---

## 2. The .env File Is the Single Point of Failure

The `bootstrap.sh` script will create `.env` interactively, but your CLI agent may not handle interactive prompts well. **Create `.env` yourself before the agent starts:**

```bash
cd /mnt/agents/output/AURA
cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-real-key-here
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_EMAIL=admin@aura.local
ADMIN_PASSWORD=change-this-password
LOG_LEVEL=INFO
TOKEN_BUDGET_DAILY=1000000
MAX_CONCURRENT_AGENTS=50
AGENT_TIMEOUT_SECONDS=300
EOF
```

**Critical rules for JWT_SECRET**:
- Minimum 16 characters (the code enforces this)
- Use `openssl rand -hex 32` to generate a proper one
- Never use `change-me` or `secret` — the code warns about defaults
- Save this somewhere — if you lose it, all existing JWT tokens become invalid

**OPENAI_API_KEY**: The LLM gateway will fail to start without this. Use a real key. If you don't have one, the gateway health check will fail, which means the core service readiness check will fail, which means Phase C and E will fail.

---

## 3. The Code Is Scaffolded, Not Production-Ready

**What IS implemented**:
- All Pydantic models (12 files)
- Event bus with pub/sub and ring buffer
- SQLite connection factory with WAL + FK
- Migration runner (16 migrations, 0-015)
- All SQL schemas with triggers, FTS5, pre-seeded data
- LLM gateway with cache, budget, retry logic
- WebSocket server with ConnectionManager + SSE fallback
- Core service with 11 API routers, JWT auth, RBAC
- All 3 injection frameworks (validation, memory, charter)
- BaseAgent ABC with heartbeat, progress, LLM calling
- Docker Compose stack with health checks
- React dashboard skeleton with routing
- Makefile, bootstrap script, backup script

**What is NOT fully implemented** (your agent must complete these):

| Gap | Why | What Your Agent Must Do |
|-----|-----|------------------------|
| **No actual agent executables** | BaseAgent ABC exists but no `if __name__ == "__main__"` entry points wired to `AGENT_TYPES` registry | Wire each agent type into the CLI registry, ensure `python -m aura_agents.learning` works |
| **No circuit breaker implementation** | Spec defines 3-state FSM, but no code | Implement `CircuitBreakerManager` with CLOSED/OPEN/HALF_OPEN states |
| **No watchdog implementation** | Spec defines heartbeat→SIGTERM→SIGKILL chain | Implement `WatchdogManager` that monitors agent PIDs |
| **Dashboard pages are stubs** | Only Command Center has real code; other 11 pages are `<Placeholder />` | Implement each page incrementally (P2 work, can defer) |
| **No validation test functions registered** | `_TEST_REGISTRY` is empty except 2 placeholders | Write actual test functions for the 20 categories |
| **No real WebSocket live event streaming** | SSE endpoint has hardcoded heartbeats | Wire event bus to WebSocket broadcast |
| **LLM gateway mock mode** | Requires real OpenAI API key for actual calls | Add a mock/test mode that returns canned responses |

---

## 4. How to Detect Fake Success (Critical)

Your CLI agent may declare things working when they are not. **Do not trust these statements:**

| What the agent might say | What you should verify |
|--------------------------|----------------------|
| "All imports successful" | Run the imports yourself in a fresh Python process. `python -c "import aura_sdk"` is not enough — test the specific submodules. |
| "Health check passes" | `curl` the endpoint yourself. Check the response body, not just HTTP 200. |
| "Database migrations applied" | `sqlite3 /data/aura.db ".tables"` — count the tables. Should be 30+. |
| "All tests pass" | The test files are mostly stubs. Passing stubs means nothing. Check if tests actually exercise logic. |
| "Service is running" | `docker compose ps` shows status. `curl` the health endpoint. Check logs for errors. |
| "Docker Compose works" | `docker compose logs` may show crash loops. A container that restarts every 10s is "running" but broken. |

**Always verify independently.** Run the curl commands. Check the logs. Look at the actual HTTP response body.

---

## 5. Common Failure Modes (So You Can Spot Them Early)

### Import Errors (Phase A)

```
ModuleNotFoundError: No module named 'aura_sdk'
```
**Cause**: `pip install -e` not run, or run from wrong directory.
**Fix**: Must run from inside `workspace/aura-sdk/` directory.

```
ImportError: cannot import name 'StrEnum' from 'enum'
```
**Cause**: Python < 3.12.
**Fix**: Upgrade Python. No workaround.

### JWT Secret Too Short (Phase E)

```
Config issue: JWT_SECRET must be at least 16 characters
```
**Cause**: `.env` has short/default secret.
**Fix**: Regenerate with `openssl rand -hex 32`.

### LLM Gateway Not Reachable (Phase E)

```
llm_gateway_health_check_failed
```
**Cause**: LLM gateway container not running, or wrong URL in env.
**Fix**: `docker compose logs llm-gateway` — probably missing OPENAI_API_KEY.

### SQLite Permission Denied (Phase B)

```
unable to open database file
```
**Cause**: `/data/aura.db` path in container doesn't match volume mount.
**Fix**: Check `docker-compose.yml` volume mounts. Ensure `aura-data` volume exists.

### Dashboard 502/503 (Phase F)

```
curl: (7) Failed to connect to localhost:3000
```
**Cause**: Dashboard container not running, or nginx config error.
**Fix**: `docker compose logs aura-dashboard` — likely the `dist/` directory wasn't built.

---

## 6. When to Intervene vs. When to Let It Run

### Let the agent work independently when:
- Installing packages and fixing import errors
- Writing unit tests for existing code
- Refactoring for style/consistency
- Adding missing boilerplate (docstrings, type hints)

### **STOP and intervene when**:
- The agent wants to switch databases (SQLite → PostgreSQL)
- The agent wants to add infrastructure (Redis, RabbitMQ, K8s)
- The agent wants to rewrite the architecture
- The agent declares a phase complete but acceptance criteria aren't verified
- The agent generates code it hasn't actually tested
- The agent says "this should work" without running it

### Emergency override:
If the agent is going off-track, paste this:

```
STOP. Do not proceed. Return to the last validated phase.
Do not add new infrastructure. Do not switch technologies.
Fix the current issue within the existing architecture.
```

---

## 7. Time Expectations (Realistic)

| Phase | Estimated Time | Why |
|-------|---------------|-----|
| A (SDK install) | 10-30 min | Mostly dependency resolution |
| B (Migrations) | 15-30 min | Quick if SQLite is available |
| C (LLM gateway) | 20-40 min | May need mock mode if no API key |
| D (WS server) | 20-30 min | Simple service |
| E (Core service) | 1-2 hours | Most complex — 11 routers to validate |
| F (Docker Compose) | 30-60 min | Build times dominate |
| G (Agent runtime) | 30-60 min | May need entry point wiring |
| H (Validation) | 20-30 min | Framework is ready, needs test functions |
| I (Memory CRUD) | 20-30 min | CRUD is implemented |
| J (Charter enforcement) | 20-30 min | Enforcement code is ready |

**Total realistic time: 4-7 hours** for a thorough agent, assuming it doesn't rush.

If the agent completes all 10 phases in under 2 hours, **it probably skipped validation**.

---

## 8. Security Before You Start

1. **The `.env` file contains your OpenAI API key** — ensure it's in `.gitignore` (it is)
2. **The default admin password** (`admin123`) is in `.env.example` — change it in your real `.env`
3. **JWT_SECRET** — if compromised, anyone can forge tokens. Generate a proper random one.
4. **Dashboard runs on port 3000** — if exposed to the internet, add HTTPS/reverse proxy
5. **SQLite database** — ensure the `data/` directory has restricted permissions (`chmod 700 data/`)

---

## 9. What Good Phase Completion Looks Like

A honest phase completion report from your agent should include:

```
PHASE [X] COMPLETE: [Name]

Acceptance Criteria:
  [PASS] Criterion 1 — evidence: <specific output>
  [PASS] Criterion 2 — evidence: <specific output>
  [FAIL] Criterion 3 — evidence: <specific error> — FIX: <what was done>

Files Modified:
  - path/to/file.py (reason)

Known Issues:
  - Issue description and impact
  - Whether it blocks the next phase

Ready for Phase [X+1]: YES/NO
Next Phase Blockers: <none or specific issues>
```

**If the report doesn't look like this, ask the agent to redo it with evidence.**

---

## 10. The Constitutional Non-Negotiables

If your agent tries to violate any of these, **stop it immediately**:

| Rule | Why | Agent Might Try... |
|------|-----|-------------------|
| SQLite only (not PostgreSQL) | P2 team scale | "Let's add PostgreSQL for reliability" → NO |
| Docker Compose only (not K8s) | P2 simplicity | "Let's prepare K8s manifests" → NO |
| In-memory event bus | P2 no external deps | "Let's add Redis" → NO |
| Single LLM provider (OpenAI) | P2 simplicity | "Let's add Anthropic fallback" → NO |
| CLI agents only (never in-process) | Process isolation | "Let's make agents Python classes" → NO |
| 8 subsystems (frozen) | Architecture contract | "Let's add a 9th subsystem" → NO |
| Append-only audit ledger | Tamper evidence | "Let's allow admin to delete audit entries" → NO |
| Human approval for high-risk | Charter enforcement | "Let's auto-approve after timeout" → NO |

---

## Final Checklist Before You Say "Go"

- [ ] Python 3.12+ installed
- [ ] Docker running (daemon or Desktop)
- [ ] `.env` file created with real `OPENAI_API_KEY`
- [ ] `.env` file has strong `JWT_SECRET` (32+ hex chars)
- [ ] `.env` has non-default `ADMIN_PASSWORD`
- [ ] `data/` directory has restricted permissions
- [ ] You have the handoff prompt ready to paste
- [ ] You know how to check `docker compose ps`
- [ ] You know how to check `docker compose logs`
- [ ] You know the 10 phases and their acceptance criteria
- [ ] You know the 9 constitutional non-negotiables
- [ ] You understand what "fake success" looks like and how to detect it

---

*If all boxes are checked, you're ready. Paste the handoff prompt to your CLI agent and let it begin with Phase A.*

*Remember: The agent works for you. You have override authority. Human governance is final.*
