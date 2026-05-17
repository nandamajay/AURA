# Baseline Lock Report

Generated: 2026-05-18
Purpose: Immutable stabilization origin checkpoint before controlled P0 stabilization work.

## Lock Anchors

- Main integration lock commit: `50053b43cc93a30278a4ff567ac0f25f5ff92167`
  - Commit message: `docs(governance): bootstrap repository policies and contribution controls`
- Discovery baseline tag: `discovery-phase-baseline`
- Discovery baseline tag hash: `a4ea482a4021d22e512e44eb5a6de7bb880549a9`

## Branch Topology (at lock)

- `main`
- `stabilization/p0-critical-enforcement`
- `stabilization/p1-runtime-reliability`
- `stabilization/p2-distributed-hardening`
- `feature/dashboard-evolution`
- `feature/plugin-runtime`
- `research/maintainer-learning-engine`

## Preserved Artifacts

- Runtime discovery evidence JSON:
  - `AURA/data/outputs/runtime_discovery/runtime_discovery_20260517T193152Z-kieleu.json`
  - `AURA/data/outputs/runtime_discovery/runtime_discovery_supplement_20260517T193501Z-ec55vs.json`
- Discovery baseline document:
  - `DISCOVERY_BASELINE.md`
- Safety and integration records:
  - `SAFE_TO_PUSH_REPORT.md`
  - `AURA_GITHUB_INTEGRATION_REPORT.md`

## Replay Evidence Snapshot

- Replay stress and integrity findings are preserved in runtime discovery JSON artifacts above.
- Baseline includes observed mutation drift and partial/crash replay behavior evidence.

## Governance Snapshot

- Governance bootstrap policy docs committed:
  - `GOVERNANCE_BOOTSTRAP.md`
  - `.github/CODEOWNERS`
  - PR/Issue templates
  - `SECURITY.md`
  - `CONTRIBUTING.md`

## Runtime Discovery Snapshot

- Coverage preserved for:
  - concurrency
  - replay stress
  - WAL contention
  - watchdog pressure
  - governance races
  - websocket/SSE instability
  - failure injection
  - corruption scenarios

## Integrity Rule

This lock report marks the immutable origin for stabilization.
No mutation of baseline tag, preserved discovery artifacts, or historical findings is permitted during stabilization.
