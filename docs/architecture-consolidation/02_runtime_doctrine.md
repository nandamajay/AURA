# AURA Runtime Doctrine

Date: 2026-05-18

## Operational Doctrine
1. Determinism over throughput when these conflict.
2. Audit visibility over silent recovery.
3. Replay lineage over convenience shortcuts.
4. Explicit bounded behavior over false absolute guarantees.
5. Evidence before architecture evolution.

## Execution Doctrine
- Every high-risk transition must be explainable and replay-visible.
- Failures are first-class outputs; no silent auto-fix behavior.
- Queue/retry/event ordering must remain inspectable with lineage metadata.
- Broadcast is downstream of persistence; unpersisted events are not fanned out.

## Stability Doctrine
- Prefer explicit state machines and transactional boundaries.
- Keep single-node simplicity unless evidence thresholds are exceeded.
- Preserve current platform shape (SQLite + Docker Compose + in-memory bus) during consolidation phases.

## Reporting Doctrine
- Classify outcomes as `guaranteed`, `strong but bounded`, `best effort`, `experimental`, or `out of scope`.
- Never collapse bounded behavior into success language.
- Report residual risk and confidence limits with evidence references.
