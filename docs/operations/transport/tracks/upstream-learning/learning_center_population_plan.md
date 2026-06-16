# M9 Learning Center Population Plan

## Current State (implemented)

### Existing ingestion paths
- Learning Center panels read only memory endpoints:
  - `/api/v1/memory/summary`
  - `/api/v1/memory/learning/timeline`
  - `/api/v1/memory/decisions`
  - `/api/v1/memory/failures`
  - `/api/v1/memory/replay-incidents`
- Knowledge evidence index provides raw file listing/read for fixed roots (`evidence`, `docs/operations/transport`, etc.).

### Missing for M8 learning reuse
- No typed ingestion of Track-B M8 artifacts into Learning Center.
- No automatic conversion of M8 audit/closure/readiness/release outputs into reusable knowledge entries.
- No dedup policy between memory ledgers and file-based reports.
- No release-tag indexing into learning surfaces.

## Required Auto-Ingestion Targets
1. Audit reports
2. Closure reports
3. Readiness reports
4. Release reports
5. Validation reports
6. Defect reports
7. Schema freeze records
8. Release tags

## Proposed Ingestion Architecture (implementation-ready)

### A. Source adapters
- `File-report adapter` (docs/operations/transport + governed report directories)
- `Track-B manifest adapter` (reads `track_b_artifact_manifest.json` and execution artifact)
- `Git metadata adapter` (release tags + tag->commit linkage)

### B. Canonical ingestion metadata (mandatory)
- `record_id` (deterministic hash)
- `record_type` (audit/closure/readiness/release/validation/defect/schema_freeze/release_tag)
- `artifact_name`
- `schema_version`
- `classification`
- `task_id` / `session_id` (if present)
- `platform`
- `generated_at`
- `artifact_sha256`
- `source_path`
- `source_commit_sha`
- `lineage_refs[]`
- `evidence_refs[]`
- `ingested_at`
- `ingestion_status` (`PASS`/`FAIL_CLOSED`)

### C. Indexing strategy
- Deterministic scan order: path asc, filename asc, mtime asc.
- Upsert key: `(record_type, artifact_sha256)`.
- Reject ingestion when mandatory metadata missing.
- Maintain immutable versioned entries; no in-place mutation.

### D. Lineage back-links
- Add backlinks from ingested learning entry to:
  - component identifiers
  - M8 decision/readiness artifacts
  - evidence IDs and source artifact SHA
  - release tag + commit

### E. Searchability requirements
- Filter by `platform`, `record_type`, `classification`, `decision_state`, `readiness_status`, `conflict_type`, `release_tag`, `date range`.
- Full-text search across summaries + selected fields.

## Duplicate/Stale Source Controls
- Duplicate detection: same `artifact_sha256` + `record_type` => collapse to one canonical entry.
- Stale detection: latest release tag points to commit newer than latest ingested report.
- Drift alert: schema freeze version mismatch against ingested artifact schema version.

## Priority Plan
- P0: typed M8 ingestion + metadata normalization + Learning Center widgets.
- P1: release-tag indexing + stale/duplicate controls.
- P2: cross-release trend analytics.
