# Snapshot-Bound Engineering Workflow Runtime

## API Surface
- `POST /api/v1/engineering/snapshots/freeze`
- `POST /api/v1/engineering/workflows`
- `POST /api/v1/engineering/workflows/{workflow_id}/task`
- `POST /api/v1/engineering/workflows/{workflow_id}/transition`
- `POST /api/v1/engineering/workflows/{workflow_id}/validation/run`
- `POST /api/v1/engineering/workflows/{workflow_id}/governance/request`
- `POST /api/v1/engineering/workflows/{workflow_id}/governance/decision`
- `POST /api/v1/engineering/workflows/{workflow_id}/lineage/retry`
- `POST /api/v1/engineering/workflows/{workflow_id}/lineage/finalize`
- `POST /api/v1/engineering/workflows/{workflow_id}/evidence`
- `GET /api/v1/engineering/workflows/{workflow_id}/reconstruct`
- `GET /api/v1/engineering/workflows/{workflow_id}`
- `GET /api/v1/engineering/workflows`

## Deterministic Workflow Rules
1. Snapshot freeze must reference approved provenance intake + source snapshot.
2. Workflow creation must bind to immutable snapshot.
3. Engineering task binding injects required provenance anchors.
4. Detached engineering tasks are rejected at `/api/v1/tasks`.
5. Validation results are persisted per-tool and replay-visible.
6. Governance transitions are explicit, append-only, audit-visible.
7. Lineage finalization requires explicit approved governance action.
8. Replay reconstruction failure invalidates workflow replay trust.
