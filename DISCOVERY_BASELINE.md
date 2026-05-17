# Discovery Baseline

Timestamp (UTC): 2026-05-17T19:31:52Z to 2026-05-17T19:33:52Z (main campaign), 2026-05-17T19:35:01Z to 2026-05-17T19:35:23Z (supplemental campaign)
Baseline scope: adversarial runtime discovery and stabilization assessment only

## Architecture Maturity State

- Replay integrity: partially validated under pressure.
- Watchdog lifecycle: validated with timeout and escalation evidence.
- Governance enforcement: partially validated; contention and escalation path failures observed.
- Truthful failure reporting: validated with intentional failure injection.
- Architecture enforcement: partial runtime evidence, not full hard guarantees.
- CI/replay enforcement: partially present, additional gates required.

## Runtime Truth Artifacts

- `AURA/data/outputs/runtime_discovery/runtime_discovery_20260517T193152Z-kieleu.json`
- `AURA/data/outputs/runtime_discovery/runtime_discovery_supplement_20260517T193501Z-ec55vs.json`

## Runtime Truth Findings

- Concurrency:
  - 20+ parallel tasks observed with overlapping execution.
  - Mixed workload confirmed (completed and cancelled outcomes in same run).
- Event ordering pressure:
  - Duplicate delivery observed.
  - Non-monotonic retry ordering observed.
  - Burst pressure caused bounded replay/drop behavior.
- SQLite WAL pressure:
  - Real `database is locked` failures observed under forced write lock.
  - Recovery observed when lock duration, retries, and wait policy aligned.
- Replay stress:
  - Replay snapshot drift observed under concurrent mutation.
  - Corrupted replay payloads correctly raised errors.
  - Partial/crash logs replay differently from finalized logs (integrity false).
- Watchdog:
  - Timeout detection and SIGTERM/SIGKILL flows observed.
  - Event emission observed; replay persistence for watchdog stream is not automatic.
- WS/SSE:
  - Slow-consumer delivery skew and recipient fluctuation observed under reconnect pressure.
- Governance:
  - Conflicting concurrent approval writes showed race/last-writer behavior.
  - Escalate action triggered server-side 500 due audit event constraint mismatch.

## Known Weaknesses

- Governance escalate path can fail with audit event-type constraint violation.
- Approval conflict handling is race-sensitive (non-deterministic final state under concurrency).
- Event retry ordering is not strictly monotonic under burst conditions.
- Replay under concurrent mutation lacks stable snapshot semantics.
- WAL contention can starve writers when lock hold exceeds retry/backoff envelope.
- Transport fanout fairness degrades significantly for slow consumers.

## Stabilization Roadmap Reference

Priority order (discovery-backed):
1. Governance critical-path enforcement and deterministic conflict handling.
2. WAL contention resilience and starvation prevention.
3. Replay snapshot isolation and deterministic replay boundary enforcement.
4. Event ordering/retry contract hardening.
5. WS/SSE backpressure and slow-consumer containment.

This baseline is the immutable reference point for post-discovery stabilization branches.
