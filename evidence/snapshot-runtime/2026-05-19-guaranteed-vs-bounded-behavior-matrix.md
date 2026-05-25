# Guaranteed vs Bounded Behavior Matrix

Date: 2026-05-19

## Guaranteed
- Engineering snapshots are immutable (`UPDATE/DELETE` blocked).
- Detached engineering task creation is rejected when provenance anchors are missing.
- Workflow transitions are bounded by explicit deterministic state map.
- Governance decisions are persisted append-only and audit-visible.
- Replay reconstruction failure invalidates workflow replay trust.

## Strong but Bounded
- External validation tools (`checkpatch`, `sparse`, `clang_build`) are integrated as availability/version probes.
- Validation drift detection is deterministic against snapshot-declared versions.
- Governance override of failed validation is allowed only with stronger role and explicit reason.

## Best Effort
- External tool execution depth is bounded by local tool availability and probe mode.
- Clang build probe runs only when build probe file is provided.

## Not Guaranteed in This Phase
- Full kernel build/test orchestration beyond bounded probes.
- Full plugin sandbox isolation (this phase enforces boundaries, not process sandboxing).
- Autonomous learning or self-modifying pipeline behavior (explicitly out of scope).
