# Replay Lineage Report

Date: 2026-05-18

## Objective
Validate replay-safe lineage preservation for source intake lifecycle, including retry and rebase semantics.

## Evidence Source
- `evidence/provenance/2026-05-18-source-provenance-runtime-evidence.json`
- `AURA/services/core/tests/test_provenance_runtime.py`

## Executed Lineage Flow
1. Source intake approved.
2. Replay snapshot created.
3. Two explicit retry lineage entries recorded.
4. Explicit rebase lineage entry recorded.
5. Reconstruction executed twice.

## Runtime Results
- Event lineage stages observed:
  - `retry_recorded`, `retry_recorded`, `rebase_recorded`
- Retry sequence metadata observed:
  - first retry `retry_sequence=1`
  - second retry `retry_sequence=2`
- Rebase metadata observed:
  - `explicit_rebase=true`
  - commit anchors present in payload
- Reconstruction hash deterministic across reruns:
  - `809ff82d7c9c056bea901aba94e4f40d698d6fda2fe0f440fd58574bb0c8e88c`

## Ordering Integrity Note
- Runtime defect discovered during initial validation:
  - same-second lineage writes could reorder due to random text primary key ordering.
- Corrective update applied:
  - lineage fetch order changed to `ORDER BY created_at, rowid`.
- Post-fix outcome:
  - deterministic lineage progression under tested retry/rebase sequence.

## Replay Conclusion
- Replay lineage is reconstructable and deterministic for tested intake lifecycle.
- Replay boundary remains bounded by persisted events/snapshots only; no hidden mutable replay path added.
