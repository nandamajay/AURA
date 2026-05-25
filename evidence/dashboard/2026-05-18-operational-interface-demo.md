# Operational Interface Demo Artifact

Date: 2026-05-18
Branch: `stabilization/p1-runtime-reliability`

## Surfaces Implemented
- Runtime dashboard: `AURA/dashboard/src/pages/GlobalCommandCenter.tsx`
- Replay explorer + evidence browser: `AURA/dashboard/src/pages/DebuggingCenter.tsx`
- Governance timeline viewer: `AURA/dashboard/src/pages/GovernanceCommandCenter.tsx`
- Domain observability + pressure: `AURA/dashboard/src/pages/LiveAgentObservability.tsx`

## Backend Operational Endpoints Added
- `GET /health/runtime-overview`
- `GET /api/v1/knowledge/evidence/index`
- `GET /api/v1/knowledge/evidence/read`
- `GET /api/v1/tasks/{task_id}/replay/state`

## Build Validation
Command:
`cd AURA/dashboard && npm run build`

Result:
- build succeeded
- bundle generated in `AURA/dashboard/dist`

## Test Validation
Command attempted:
`cd AURA/services/core && PYTHONPATH=src:../../workspace/aura-sdk/src pytest -q tests/test_operational_interface_endpoints.py ...`

Status:
- blocked by missing local python deps (`fastapi`, `aiosqlite`) in current shell environment
- syntax validation of changed python files completed via AST parse

## Manual Screenshot Capture Guide
1. Start stack (`make up` from `AURA/`).
2. Login to dashboard.
3. Capture:
   - `/` runtime dashboard cards + alert surface
   - `/debug` replay boundary + evidence browser
   - `/governance` timeline + ordering summary
   - `/agents` per-domain coexistence pressure
4. Store images under `evidence/dashboard/screenshots/`.

## Truthfulness Note
This artifact reports implementation and validation status only. It does not claim production readiness or unbounded deterministic guarantees.
