# Plugin Lifecycle Documentation

## Scope
Portable runtime stabilization lifecycle for target plugins under fail-closed governance.

## Lifecycle States
1. `load`
2. `negotiate`
3. `validate`
4. `activate`
5. `quarantine`
6. `unload`
7. `replay_restore`

## Deterministic Behavior Rules
- Lifecycle execution is ordered and append-only.
- Any plugin contract failure transitions to `quarantine` and then `unload`.
- `replay_restore` is allowed only when replay compatibility is not `INCOMPATIBLE`.
- Quarantined plugins cannot be loaded until quarantine is explicitly cleared.

## Fail-Closed Semantics
- Invalid plugin contract -> `FAIL_CLOSED`.
- Unsupported topology provider -> quarantine + `FAIL_CLOSED`.
- Replay incompatibility -> quarantine + `FAIL_CLOSED`.
- Missing target selection -> `FAIL_CLOSED`.

## Core/Plugin Boundary
- Core runtime controls lifecycle orchestration only.
- Target-specific route/topology/mixer/evidence logic is plugin-owned only.
- Core runtime does not branch on `if target == ...`.
