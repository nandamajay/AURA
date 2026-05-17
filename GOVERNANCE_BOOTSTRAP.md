# Governance Bootstrap

Generated: 2026-05-18
Scope: GitHub repository governance bootstrap for AURA canonical runtime history

## Branch Protection Strategy (Recommended)

Apply branch protection to `main`:
- Require pull request before merge.
- Require at least 2 approvals.
- Require CODEOWNER review.
- Dismiss stale approvals on new commits.
- Require linear history.
- Require signed commits (if org policy supports it).
- Block force-push and branch deletion.
- Require conversation resolution before merge.

Apply lighter protections to stabilization branches:
- Require pull request before merge.
- Require at least 1 approval.
- Block force-push.

## Required Checks (Recommended)

Set these as required checks on `main`:
- `ci/lint-and-unit`
- `ci/architecture-enforcement`
- `ci/governance-enforcement`
- `ci/replay-integrity`
- `ci/determinism-smoke`

Note:
- These check names are the target policy names; workflow implementation can be phased in.

## CODEOWNERS Strategy

Use ownership boundaries:
- Global: `@nandamajay`
- Core orchestration/services: `@nandamajay`
- SDK/replay/governance/validation: `@nandamajay`
- Dashboard: `@nandamajay`
- Schemas/migrations: `@nandamajay`
- Docs/policy: `@nandamajay`

## PR Requirements

PR template enforces:
- runtime finding reference,
- affected subsystem(s),
- replay/audit impact declaration,
- deterministic impact declaration,
- rollback strategy,
- evidence links.

## Issue Templates

Added:
- bug report (runtime/regression path),
- stabilization task (finding-driven correction path).

## Security Policy

Added `SECURITY.md` with:
- reporting channel expectations,
- prohibited secret handling,
- disclosure workflow.

## Contributing Guide

Added `CONTRIBUTING.md` with:
- branch workflow,
- commit quality requirements,
- test and evidence expectations,
- no-history-rewrite policy.

## ADR Template

Added `docs/adr/0000-adr-template.md` for architecture decision records with:
- context,
- decision,
- consequences,
- replay/governance impact fields.

## Governance Bootstrap Status

- [x] Strategy documented
- [x] CODEOWNERS added
- [x] PR template added
- [x] Issue templates added
- [x] Security policy added
- [x] Contributing guide added
- [x] ADR template added
- [ ] Branch protection toggles applied in GitHub UI/API (manual platform operation)
