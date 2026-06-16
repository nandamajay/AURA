# M10 Intelligence API Spec

## Base
`/api/v1/track-b-intel`

## Endpoints
- `GET /overview`
  - Aggregate payload containing trends, patterns, recommendations, learning intelligence, executive summary, and forecast.
- `GET /trends`
  - Cross-release trends: audit, release, readiness, dependency, conflict.
- `GET /patterns`
  - Pattern mining for failures, dependencies, conflicts, readiness blockers.
- `GET /recommendations`
  - Evidence-backed recommendations with lineage references.
- `GET /learning`
  - Learning clusters, deduped lessons, stale clusters.
- `GET /executive`
  - Project health, release health, blocker summary.
- `GET /forecast`
  - Deterministic readiness probability, risk level, remaining work estimate.

## Determinism
- Sorting applied across all arrays and dictionaries.
- Results derived only from existing M8/M9 artifacts and reports.

