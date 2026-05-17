# AURA P1 — Operational Governance Layer: Master Index
## 18 Artifacts | Built on Frozen P0 Foundation | Anti-Overengineering Applied
### Status: SPECIFICATION COMPLETE

---

## GOVERNANCE CONSTRAINTS APPLIED

### Anti-Overengineering Governor (AOG)
Every artifact was challenged with:
1. Is this required for MVP? → Only Phase 1 features included
2. Can this be simpler? → Yes: SQLite not PostgreSQL, Compose not K8s
3. Can this remain modular without distribution? → Yes: in-memory bus, local-first
4. Will this increase operational burden? → Minimized: no external monitoring deps
5. Does this improve determinism? → Yes: explicit contracts, replay logging
6. Does this improve observability? → Yes: structured logs, typed events
7. Does this improve maintainability? → Yes: explicit state machines, clear docs
8. Is this solving a real constraint? → Verified against original 11 specs

### Architectural Hallucination Defense (AHD)
Every subsystem justified with:
- Concrete operational purpose
- Measurable benefit
- Clear integration boundary
- Maintenance cost estimate

### Human Maintainability Enforcement (HME)
Every workflow provides:
- Architecture diagram reference
- Sequence diagram reference
- Failure flow diagram
- Operational playbook
- Troubleshooting entry point
- Debuggability guarantee

---

## P0 FROZEN FOUNDATION (Immutable)

| P0 Artifact | File | Status |
|-------------|------|--------|
| Monorepo + Workspace + SDK | `phase0/01_monorepo_workspace_sdk.md` | FROZEN |
| Services + Docker Topology | `phase0/02_services_docker_topology.md` | FROZEN |
| SQLite Schema + Migrations | `phase0/03_sqlite_schema_migrations.md` | FROZEN |
| Events + WebSocket + Auth | `phase0/04_events_websocket_auth.md` | FROZEN |
| Watchdog + Circuit + Testing | `phase0/05_watchdog_circuit_testing_ci.md` | FROZEN |
| Plugins + Replay + DevOps | `phase0/06_plugins_replay_devops.md` | FROZEN |

**P1 may not violate any P0 contract, boundary, or rule.**

---

## P1 ARTIFACT MAP

| # | Artifact | Doc | Areas |
|---|----------|-----|-------|
| 1 | Security + Sandboxing Policy | `01_security_sandboxing.md` | Threat model, agent isolation, seccomp, RBAC |
| 2 | Failure Recovery Playbook | `01_security_sandboxing.md` | 8 failure categories, 4 recovery procedures |
| 3 | Watchdog Governance Rules | `02_watchdog_circuit.md` | Heartbeat spec, termination chain, restart policy |
| 4 | Circuit Breaker Governance | `02_watchdog_circuit.md` | State machine, per-agent isolation, metrics |
| 5 | Agent Isolation Policy | `01_security_sandboxing.md` | Process isolation, resource limits, FS restrictions |
| 6 | Secret Management Policy | `01_security_sandboxing.md` | Docker secrets, env var policy, rotation |
| 7 | Runtime Execution Policy | `03_runtime_cost.md` | Scheduling rules, priority inversion, starvation |
| 8 | Replay Recovery Policy | `04_replay_backup.md` | Recording guarantees, replay fidelity, snapshots |
| 9 | Backup + Restore Strategy | `04_replay_backup.md` | SQLite backup, WAL checkpoint, daily automation |
| 10 | Disaster Recovery Playbook | `04_replay_backup.md` | Failure scenarios, recovery procedures, RTO/RPO |
| 11 | Operational Monitoring Playbook | `05_monitoring_observability.md` | Metrics, alerts, health checks, diagnostics |
| 12 | Observability Governance Rules | `05_monitoring_observability.md` | Logging spec, metric taxonomy, trace schema |
| 13 | Runtime Cost Governance | `03_runtime_cost.md` | Token budgets, LLM routing, cost attribution |
| 14 | Resource Budget Enforcement | `03_runtime_cost.md` | CPU/memory/disk limits, cgroup enforcement |
| 15 | Plugin Trust Model | `06_plugin_audit.md` | Plugin validation, sandboxing, permission model |
| 16 | Command Execution Restrictions | `01_security_sandboxing.md` | Allowed commands, deny-list, exec restrictions |
| 17 | Infrastructure Hardening Checklist | `06_plugin_audit.md` | Docker hardening, network isolation, file perms |
| 18 | Audit + Compliance Retention Rules | `06_plugin_audit.md` | Ledger retention, chain hash, compliance export |

**P1 Artifact Files:**
- `p1/01_security_sandboxing.md` (Artifacts 1, 2, 5, 6, 16)
- `p1/02_watchdog_circuit.md` (Artifacts 3, 4)
- `p1/03_runtime_cost.md` (Artifacts 7, 13, 14)
- `p1/04_replay_backup.md` (Artifacts 8, 9, 10)
- `p1/05_monitoring_observability.md` (Artifacts 11, 12)
- `p1/06_plugin_audit.md` (Artifacts 15, 17, 18)
