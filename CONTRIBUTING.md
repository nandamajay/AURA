# Contributing

## Workflow

- Base branch: `main`
- Use topic branches:
  - `stabilization/*`
  - `feature/*`
  - `research/*`
- No direct pushes to `main`.

## Commit Quality

Each commit must be scoped and verifiable:
- issue/finding reference,
- affected subsystem,
- replay impact,
- deterministic impact,
- rollback strategy.

Avoid vague cleanup commits and mixed unrelated changes.

## Testing and Evidence

Before PR:
- run relevant tests,
- produce runtime evidence for behavioral fixes,
- include replay/audit evidence when applicable.

## Safety Rules

- No history rewrites on shared branches.
- No secret or credential commits.
- Preserve discovery evidence and baseline lineage.
