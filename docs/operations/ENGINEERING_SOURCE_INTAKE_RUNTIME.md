# Engineering Source Intake Runtime

## Endpoints
- `POST /api/v1/provenance/sources/register`
- `POST /api/v1/provenance/sources/{intake_id}/validate`
- `POST /api/v1/provenance/sources/{intake_id}/approve`
- `POST /api/v1/provenance/sources/{intake_id}/override-trust`
- `POST /api/v1/provenance/sources/{intake_id}/snapshot`
- `POST /api/v1/provenance/sources/{intake_id}/lineage`
- `POST /api/v1/provenance/sources/{intake_id}/lineage/retry`
- `POST /api/v1/provenance/sources/{intake_id}/lineage/rebase`
- `GET /api/v1/provenance/sources/{intake_id}`
- `GET /api/v1/provenance/sources/{intake_id}/reconstruct`
- `GET /api/v1/provenance/sources`

## Deterministic Intake Pipeline
1. Register canonical source intake.
2. Validate source metadata.
3. Classify trust (`trusted`, `bounded-trust`, `untrusted/manual-review-required`).
4. Enforce operator approval policy.
5. Create immutable replay snapshot after approval.
6. Record explicit lineage hooks for retry/rebase.
7. Reconstruct exact persisted engineering state via `/reconstruct`.

## Enforcement Boundaries
- `source_intakes` are immutable.
- `source_intake_events`, `source_lineage_entries` are append-only.
- Trust overrides are audit-visible (`audit_ledger`).
- Untrusted intake approval requires approver/architect/admin roles.
- No autonomous-learning behavior is included in this phase.
