# CI / Runtime Parity Mapping

Date: 2026-05-18

## Shared Validation Entry Point
Both CI and local parity now use:
- `AURA/scripts/ci-parity.sh`

GitHub workflow:
- `.github/workflows/architecture-compliance.yml`

## Parity Pipeline Steps
1. Deterministic dependency sync via `scripts/env-sync.sh --no-venv`.
2. Architecture enforcement via `scripts/architecture-enforce.py`.
3. Governance/replay hard-fail tests.
4. Determinism gate (`scripts/determinism-gate.py`).

## Local Host Fallback
- `ci-parity.sh` now supports mode selection:
  - `--mode local` (requires host Python 3.12)
  - `--mode docker` (runs parity in `python:3.12-slim` against mounted repo)
  - default `--mode auto` selects local first, then docker fallback
- This keeps parity executable on hosts without local Python 3.12 while preserving the same validation sequence.

## Why This Improves Reproducibility
- removes ad-hoc CI-only install behavior
- uses pinned constraints (`constraints/py312.txt`)
- aligns local and CI commands exactly
- keeps replay/governance checks first-class and deterministic

## Known Bounds
- parity assumes Python 3.12 availability
- local parity requires deterministic dependency sync success
- docker fallback uses user-level installs inside container and may emit dependency warnings from upstream packages
- container runtime parity still depends on docker host behavior

## Evidence Sources
- startup/runtime verification artifacts: `AURA/evidence/startup/`
- demo reproducibility artifacts: `AURA/evidence/demo/`
