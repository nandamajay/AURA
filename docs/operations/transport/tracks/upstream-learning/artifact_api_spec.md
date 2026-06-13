# Track-B Artifact API Spec (M9)

## Scope
Read-only visibility APIs over frozen M8 Track-B artifacts:

- `track_b_equivalence_map.json`
- `track_b_dependency_matrix.json`
- `track_b_conflict_ledger.json`
- `track_b_equivalence_decision.json`
- `track_b_upstreaming_report.json`
- `track_b_upstreaming_readiness.json`

All endpoints are deterministic, evidence-backed, and additive. No M8 schema contracts are modified.

## Base
`/api/v1/track-b`

## Artifact APIs
- `GET /artifacts/index`
  - Query: `page`, `limit`, `include_invalid`, `strict_validation`,
    `artifact_name`, `classification`, `stage_id`, `decision_state`,
    `readiness_status`, `task_id`, `component`
  - Returns paginated artifact records with per-artifact validation and aggregate validation.
- `GET /artifacts/{artifact_id}`
  - Returns one artifact by deterministic `artifact_id`.

## Lineage APIs
- `GET /lineage`
  - Query: `component_query`, `reverse_node_id`, `include_invalid`, `strict_validation`
  - Returns lineage nodes/edges with forward navigation and reverse drill-down.

## Audit & Release Lookup APIs
- `GET /audits/index`
  - Query: `page`, `limit`
- `GET /audits/{audit_id}`
- `GET /releases/index`
  - Query: `page`, `limit`
- `GET /releases/{release_tag}`

## Dashboard APIs
- `GET /dashboard/release-summary`
- `GET /dashboard/readiness`
- `GET /dashboard/readiness-history`
- `GET /dashboard/dependency-coverage`
- `GET /dashboard/conflicts`
- `GET /dashboard/equivalence`
- `GET /dashboard/audit-history`
  - Query: `limit`
- `GET /dashboard/release-history`
  - Query: `limit`

## Learning APIs
- `GET /learning/index`
  - Query: `page`, `limit`, `strict_validation`
- `GET /learning/patterns`
  - Query: `strict_validation`

## Search API
- `GET /search`
  - Query: `q`, `kind`, `limit`, `strict_validation`
  - `kind` supports: `artifact`, `audit`, `release`, `lesson`.
  - Search covers component/symbol/dependency/conflict/audit/release/lesson/readiness text domains via indexed summaries.

## Fail-Closed Rules
- Schema freeze missing or contract validation errors keep endpoint responses available but force summary classification to `FAIL_CLOSED`.
- Lookup endpoints (`/artifacts/{id}`, `/audits/{id}`, `/releases/{tag}`) return `404` when target is not found.
- Endpoints do not synthesize placeholders for missing evidence.

## Determinism Guarantees
- Stable sorting for artifact inventory, learning index, lineage nodes/edges, and search results.
- Pagination is deterministic (`page`, `limit`) over sorted datasets.
- Artifact identities are content-addressed (`path + sha256`).

