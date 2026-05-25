# Engineering Source Intake & Provenance Runtime Report

Date: 2026-05-18  
Phase: Engineering Source Intake & Provenance Runtime

## Implemented Runtime Surface
- Migration: `AURA/knowledge/schema/019_source_provenance_runtime.sql`
  - `source_intakes` immutable authority records
  - `source_intake_events` append-only lifecycle stream
  - `source_replay_snapshots` immutable replay snapshots
  - `source_lineage_entries` append-only lineage chain
- API router: `AURA/services/core/src/core/routers/provenance.py`
  - register/validate/classify/approve/override/snapshot/lineage/reconstruct/list
- Core wiring: `AURA/services/core/src/core/main.py`
  - mounted under `/api/v1/provenance`
- Regression suite: `AURA/services/core/tests/test_provenance_runtime.py`

## Runtime Validation Executed
- Python 3.12 containerized run (deterministic install + runtime tests):
  - `services/core/tests/test_provenance_runtime.py`
  - `services/core/tests/test_governance_stabilization.py`
  - `services/core/tests/test_event_audit_persistence.py`
  - `workspace/aura-sdk/tests/test_replay.py`
- Result: `17 passed`

## Key Runtime Evidence
- Evidence capture:
  - `evidence/provenance/2026-05-18-source-provenance-runtime-evidence.json`
- Observed:
  - trusted intake path: register/validate/approve/snapshot/retry/rebase/reconstruct all `200`
  - duplicate semantic intake rejected with `409`
  - untrusted source requires approver:
    - reviewer approve `403`
    - approver approve `200`
  - override writes `audit_ledger` row (`config.changed`)
  - reconstruction hash stable across reruns

## Runtime Defect Found and Corrected During Phase
- Defect: lineage ordering drift under same-second writes (`ORDER BY created_at, id` with random text ids).
- Fix: lineage read path now orders by insertion order (`ORDER BY created_at, rowid`) in provenance router and tests.
- Result: retry/rebase lineage ordering deterministic in rerun validation.

## Scope Guardrails Honored
- No infrastructure escalation.
- No autonomous learning implementation.
- No simulated/fake provenance ingestion path.
