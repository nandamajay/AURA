# Deterministic Startup Evidence (2026-05-18)

Scope: reproducible runtime environment hardening validation (single-node, SQLite, Docker Compose).

## Executed Commands

```bash
cd AURA
./scripts/env-doctor.sh
./scripts/repro-bootstrap.sh --wait-seconds 90
./scripts/runtime-verify.sh --env-file .env --wait-seconds 90
./scripts/dependency-integrity.sh
./scripts/demo-mode.sh prepare
./scripts/demo-mode.sh up
./scripts/demo-mode.sh verify
./scripts/demo-mode.sh workload
./scripts/ci-parity.sh --mode docker
```

## Observed Results

- `env-doctor`: pass with warnings on missing host `python3.12` and missing local `.venv` (expected on docker-first host profile).
- `repro-bootstrap`: pass (stack built and started, runtime verification passed, migrations detected).
- `runtime-verify`: pass (`/health/live`, `/health/ready`, ws/llm health, protected endpoints, migration count check).
- `dependency-integrity`: pass (pip-freeze fingerprint + sha256 evidence generated).
- `demo-mode` workload: pass with deterministic seed `42`; workload report generated.
- `ci-parity --mode docker`: pass; architecture enforcement `violations=0`, tests `26 passed`, determinism gate pass.

## Generated Evidence Artifacts

- Startup/runtime verification:
  - `AURA/evidence/startup/20260518T163345Z-runtime-verify.json`
  - `AURA/evidence/startup/20260518T163554Z-runtime-verify.json`
  - `AURA/evidence/startup/20260518T163813Z-runtime-verify.json`
- Dependency integrity:
  - `AURA/evidence/startup/20260518T163350Z-dependency-integrity.json`
  - `AURA/evidence/startup/20260518T163934Z-dependency-integrity.json`
  - `AURA/evidence/startup/20260518T164356Z-dependency-integrity.json`
- Demo workload:
  - `AURA/evidence/demo/20260518T163601Z-demo-seeded-workload.json`
  - `AURA/evidence/demo/20260518T163950Z-demo-seeded-workload.json`
  - `AURA/evidence/demo/20260518T164517Z-demo-seeded-workload.json`

## Failure-First Notes

- Strict diagnostics (`env-doctor --strict`) intentionally fail when warnings exist.
- `demo-seeded-workload.py` now exits non-zero if tasks remain non-terminal at timeout, while still writing evidence (`report_status=bounded_timeout`).
- `ci-parity.sh` now supports deterministic docker fallback for hosts without local Python 3.12.
