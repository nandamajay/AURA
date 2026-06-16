# M9 Readiness Dashboard Spec (M8)

## Required Readiness Dimensions
1. M8 completion
2. Production readiness
3. Blocker count
4. Conflict count
5. Dependency coverage
6. Evidence completeness
7. Audit status
8. Release status
9. Learning-center coverage

## Current Support Review
| Dimension | Current support | Status |
|---|---|---|
| M8 completion | Not visualized | Missing |
| Production readiness | Not visualized | Missing |
| Blocker count | Not visualized | Missing |
| Conflict count | Not visualized | Missing |
| Dependency coverage | Not visualized | Missing |
| Evidence completeness | Not visualized | Missing |
| Audit status (M8) | Not visualized | Missing |
| Release status (M8 tag linkage) | Not visualized | Missing |
| Learning-center coverage (M8) | Not visualized | Missing |

## Widget Specification

### Top KPI row (cards)
- `M8 Completion %`
- `Production Readiness %`
- `Blockers`
- `Unresolved Conflicts`
- `Dependency Coverage %`
- `Evidence Completeness %`

### Readiness check matrix
- Columns: check id, status, evidence count, fail reason, linked artifacts.
- Source: `track_b_upstreaming_readiness.json` + `track_b_equivalence_decision.json`.

### Conflict + dependency panels
- Conflict severity/type distribution.
- Dependency buckets completeness and missing mandatory dependencies.
- Sources: `track_b_conflict_ledger.json`, `track_b_dependency_matrix.json`.

### Evidence integrity panel
- Provenance completeness score (required provenance fields present/missing).
- Source artifact hash integrity status.
- Sources: M8 artifact `evidence` + provenance entries.

### Audit + release panel
- Latest M8 audit report status.
- Schema freeze status + version.
- Release tag match (expected tag -> commit -> artifact run linkage).

### Learning coverage panel
- Which M8 outputs have been ingested into Learning Center typed knowledge entries.
- Missing ingestion categories and stale records.

## Fail-Closed Rendering Rules
- If required artifact unavailable or schema-invalid: show `FAIL_CLOSED` state with explicit reason.
- Never infer readiness from partial artifacts.
- Never show synthetic completion/readiness values.

## Determinism Rules
- Deterministic sort for rows: primary key asc, then generated_at asc.
- Deterministic tie-breakers for ranked sections reuse M8 ranking policy order where applicable.
- Re-rendering identical inputs must preserve value/order and hashes.
