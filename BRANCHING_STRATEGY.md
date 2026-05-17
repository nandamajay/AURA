# Branching Strategy

## Canonical Branches

- `main`
  - Protected integration branch.
  - Receives only reviewed PR merges from scoped working branches.
- `stabilization/p0-critical-enforcement`
  - Critical correctness, governance integrity, replay determinism blockers.
- `stabilization/p1-runtime-reliability`
  - Runtime resilience, contention handling, failure containment.
- `stabilization/p2-distributed-hardening`
  - Deferred hardening and scale-path readiness.
- `feature/dashboard-evolution`
  - Dashboard UX and operator visibility evolution.
- `feature/plugin-runtime`
  - Plugin runtime mechanics and isolation behavior.
- `research/maintainer-learning-engine`
  - Research-only learning/maintainer-intelligence experiments.

## Ownership Model

- `main`: architect + approver sign-off required.
- `stabilization/p0-*`: architect ownership, approver co-review mandatory.
- `stabilization/p1-*` and `stabilization/p2-*`: subsystem owner + reviewer.
- `feature/*`: feature owner + reviewer.
- `research/*`: researcher owner, no direct merge to `main` without promotion PR.

## Merge Rules

- No direct pushes to `main`.
- PR-only merges.
- Rebase/squash policy is repository-governed; no hidden history rewrites.
- Discovery baseline tag is immutable reference and must not be moved.

## Validation Gates

- Required before merge to `main`:
  - Lint/type/test pipeline green.
  - Core service startup + health checks pass.
  - Regression suite for touched subsystem passes.
  - No secret/leak findings in pre-push scan.
- Required for stabilization branches:
  - Reproduction case for defect.
  - Deterministic verification artifact for fix behavior.

## Replay Integrity Requirements

- Any change touching replay/task logging paths must include:
  - before/after replay result comparison,
  - integrity hash check evidence,
  - explicit nondeterminism impact statement.
- Replay-affecting changes cannot merge without reproducible replay artifact.

## Governance Enforcement Requirements

- Governance/audit path changes require:
  - approval-role compatible reviewer,
  - audit append-only invariants validated,
  - high-risk action gate behavior verified.
- Any action that changes approval semantics must include conflict/concurrency tests.
