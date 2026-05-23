# AURA Deterministic Runtime Setup

Date: 2026-05-18
Scope: reproducible runtime environment hardening (single-node, SQLite, Docker Compose)

## Goals
- deterministic dependency install
- reproducible bootstrap
- CI/local parity
- failure-first diagnostics
- evidence-preserving startup verification

## 1) Failure-First Diagnostics
```bash
cd AURA
./scripts/env-doctor.sh --strict
```

Strict mode blocks startup when diagnostics include failures or warnings (for example: missing local Python 3.12, missing credentials, missing deterministic constraints, or missing local `.venv`).
For runtime-only startup on hosts without local Python 3.12, use:

```bash
cd AURA
./scripts/env-doctor.sh
```

## 2) Deterministic Local Dependency Sync
```bash
cd AURA
./scripts/env-sync.sh
```

What it does:
- creates `.venv`
- installs pinned toolchain versions (`pip/setuptools/wheel`)
- installs editable workspace packages with `constraints/py312.txt`
- verifies critical imports
- captures dependency fingerprint evidence under `AURA/evidence/startup/`

## 3) Single-Command Deterministic Bootstrap
```bash
cd AURA
./scripts/repro-bootstrap.sh
```

What it does:
- strict environment doctor gate
- docker compose startup
- runtime verification (`/health`, `/health/runtime-overview`, governance/task endpoints)
- migration verification (`_migrations` count > 0)
- startup evidence artifact generation

Strict warning mode remains available when needed:

```bash
cd AURA
./scripts/repro-bootstrap.sh --strict-doctor
```

## 4) Runtime Verification (Standalone)
```bash
cd AURA
./scripts/runtime-verify.sh
```

Produces evidence in:
- `AURA/evidence/startup/*-runtime-verify.json`

## 5) Deterministic Demo Mode
```bash
cd AURA
./scripts/demo-mode.sh prepare
./scripts/demo-mode.sh up
./scripts/demo-mode.sh verify
./scripts/demo-mode.sh workload
```

Demo evidence output:
- `AURA/evidence/demo/*-demo-seeded-workload.json`
- workload command returns non-zero when tasks remain non-terminal at timeout (truthful bounded-timeout reporting)

## 6) Makefile Entry Points
```bash
make env-doctor
make env-sync
make repro-up
make repro-verify
make ci-parity
make demo-prepare demo-up demo-verify demo-workload demo-down
```

## 7) Explicit Non-Goals
- no architecture redesign
- no replay/governance semantic changes
- no distributed infrastructure escalation
- no hidden DB resets or silent wipes
