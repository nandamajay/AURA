# P0 CI Governance Hard-Fail Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `ci-governance-bypass-risk`
- Before evidence:
  - `AURA/data/outputs/runtime_discovery/ci_governance_enforcement_before_ci-governance-before-3e741ba3.json`
- Observed issue before fix:
  - CI workflow had architecture check only.
  - Governance regression suite, replay suite, and determinism gate were missing.

## Affected subsystem and code paths
- Subsystem: `S6 Governance` + `S3 Replay` + CI enforcement path
- Code paths:
  - `.github/workflows/architecture-compliance.yml`
  - `AURA/scripts/determinism-gate.py`

## Minimal correction implemented
- Upgraded workflow to `stabilization-gates` hard-fail pipeline.
- Added required CI gates:
  - architecture compliance (`architecture-enforce.py`)
  - governance/replay regression suite (`pytest` hard-fail)
  - deterministic execution verification (`determinism-gate.py`)
- Added deterministic gate script using `NondeterminismDetector` to assert:
  - deterministic sample stays deterministic
  - nondeterministic sample is detected

## Regression validation
- Local runtime equivalent of CI workflow executed in Python 3.12 container:
  - architecture enforcement
  - governance/replay pytest subset
  - determinism gate script
- Result:
  - architecture check: `violations=0`
  - pytest: `19 passed`
  - determinism gate: pass

## Runtime validation after fix
- After evidence:
  - `AURA/data/outputs/runtime_discovery/ci_governance_enforcement_after_ci-governance-after-233bcf95.json`
- Outcome:
  - all required CI signals present
  - runtime gate exit code `0`
  - `ci_governance_hard_fail_complete=true`

## Replay and deterministic impact
- Replay semantics unchanged.
- CI now blocks merges when governance/replay regressions or determinism checks fail.

## Regression risk assessment
- Medium:
  - CI duration increases due added regression suite.
  - deterministic gate intentionally emits nondeterminism warning for the probe function.

## Rollback strategy
- Revert workflow and determinism gate script changes.
- Re-run before/after CI governance artifacts to confirm gate removal.
