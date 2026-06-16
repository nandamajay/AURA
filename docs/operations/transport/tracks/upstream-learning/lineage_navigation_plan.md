# M9 Lineage Navigation Plan

## Required Navigation Chain
`Component -> Evidence -> Dependency -> Conflict -> Decision -> Readiness -> Audit -> Release`

## Current Chain Audit
| Link | Current state | Status |
|---|---|---|
| Component -> Evidence | No Track-B component viewer exists in dashboard. | Missing |
| Evidence -> Dependency | No dependency drill-down path from evidence entries. | Missing |
| Dependency -> Conflict | No conflict ledger navigation path in dashboard. | Missing |
| Conflict -> Decision | No decision linkage view in dashboard. | Missing |
| Decision -> Readiness | No readiness artifact view tied to decision. | Missing |
| Readiness -> Audit | No integrated audit linkage for M8 readiness decisions. | Missing |
| Audit -> Release | No release/tag view or release-linked audit navigation. | Missing |

## Orphan/Breakage Findings
- M8 artifacts are generated but not indexed by a dashboard-facing API.
- Evidence Browser is raw-file centric and does not establish semantic Track-B lineage hops.
- Release tag information is not exposed in dashboard navigation surfaces.

## Navigation Model (implementation-ready)

### Forward links (mandatory)
- `component_id` -> `evidence_ids[]`
- `evidence_id` -> `dependency_ids[]`
- `dependency_id` -> `conflict_ids[]`
- `conflict_id` -> `decision_id`
- `decision_id` -> `readiness_id`
- `readiness_id` -> `audit_ids[]`
- `audit_id` -> `release_id` (tag + commit)

### Reverse links (mandatory)
- `release_id` -> impacted audits/readiness/decision/conflicts/dependencies/evidence/components

### Link identity rules
- All IDs deterministic, hash-backed, and stable for identical inputs.
- All links include source artifact SHA and extraction rule ID.
- Invalid or unresolved links trigger fail-closed UI state.

## Required Drill-Down Views
1. Component detail view (anchor + corpus provenance)
2. Evidence list/detail view (provenance-complete)
3. Dependency matrix view
4. Conflict ledger view (unresolved/resolved)
5. Decision view (decision state + mandatory checks)
6. Readiness gate view
7. Audit linkage view
8. Release traceability view (tag -> commit -> artifacts)

## Priority
- P0: forward+reverse lineage edges + drill-down for all 8 chain nodes.
- P1: conflict/readiness impact traversal shortcuts.
- P2: lineage timeline animations and cross-release diffs.
