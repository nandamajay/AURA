# Lineage Integrity Report

Date: 2026-05-19

## Implemented Lineage Guarantees
- Provenance lineage hash is mandatory in workflow root.
- Retry lineage records are explicit and monotonic.
- Finalized lineage emits replay-evidence entry to source lineage table.
- No silent lineage rewrite path is exposed.

## Runtime Evidence
Coverage:
- `test_retry_lineage_is_monotonic_and_replay_failure_invalidates_trust`
- `test_snapshot_bound_end_to_end_workflow_and_reconstruction`

Observed:
- retry sequence persisted as `[1, 2]`
- lineage finalization emits replay-evidence lineage hash
- reconstruction remains trust-valid only when lineage + replay + governance are coherent

## Mutation Safety
- Lineage-bearing snapshot roots are immutable.
- append-only protections active on:
  - `engineering_workflow_events`
  - `engineering_validation_runs`
  - `engineering_governance_actions`
  - `engineering_evidence_links`
