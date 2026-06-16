# M9 Dashboard M8 Integration Plan

## Objective
Integrate all frozen M8 artifacts into the existing single dashboard system with deterministic, fail-closed, evidence-first behavior.

## Design Principles
- Reuse existing dashboard app and core API service.
- No duplicate dashboard or registry system.
- Schema-validated rendering only; invalid artifact => fail-closed card state.
- Deterministic ordering in all tables/lists.

## Target M8 Artifacts
- `track_b_equivalence_map.json`
- `track_b_dependency_matrix.json`
- `track_b_conflict_ledger.json`
- `track_b_equivalence_decision.json`
- `track_b_upstreaming_report.json`
- `track_b_upstreaming_readiness.json`

## P0 Implementation (must-have)

### 1. Core API additions (shared service)
- Add Track-B artifact index/read endpoints analogous to runtime artifacts, but Track-B scoped.
- Add response contracts for six M8 artifacts with schema validation status and fail-closed reasons.
- Add optional query filters: `task_id`, `platform`, `stage_id`, `classification`, `latest_only`.

### 2. Artifact discovery/indexing bridge
- Source registry uses existing Track-B output manifests (`track_b_artifact_manifest.json`) and execution artifact metadata.
- Indexable records include: artifact name, path, sha256, task/session linkage, platform, generated time.
- Fail closed when required metadata is missing or hash invalid.

### 3. Dashboard route + views
- Add `Track-B Upstreaming Center` page under existing nav.
- Add structured panels for each artifact:
  - Equivalence candidates/ranking
  - Dependency matrix
  - Conflict ledger
  - Decision summary
  - Upstreaming report
  - Readiness gate
- Add schema-valid badge and fail-closed reason panel for each artifact.

### 4. Readiness board widgets
- Cards: M8 completion, production readiness, blocker count, conflict count, dependency coverage, evidence completeness, audit status, release status, learning coverage.
- Source-of-truth fields come from readiness artifact + conflict/dependency/report artifacts + release metadata.

### 5. M8 lineage drill-down
- From any component row, navigate to:
  - evidence entries
  - dependency records
  - conflict rows
  - decision row
  - readiness checks
- Add reverse links (readiness -> decision -> conflict -> dependencies -> evidence -> component).

## P1 Implementation (important)
- Cross-artifact correlation widgets (e.g., unresolved conflicts affecting readiness checks).
- Decision-state timeline across repeated runs.
- Conflict taxonomy heatmap and filters.
- Remove duplicate approval nav entry (`/approval`) after compatibility window.

## P2 Implementation (nice-to-have)
- Trend visualizations across releases/tags.
- Learning-center sync freshness and stale-source indicators.
- Bulk export views for governance review packs.

## Data/Ownership Model
- Producer ownership: Track-B agent (`track_b_stage_execution.py`).
- API ownership: shared core service routers/contracts.
- Dashboard ownership: shared dashboard pages/components.
- Governance/confidence/ontology remain shared single-source (no duplication).

## Complexity Estimate
- P0: 4-6 engineering days
- P1: 2-3 engineering days
- P2: 1-2 engineering days

## Acceptance Criteria
- 100% of required M8 fields rendered in structured UI.
- Full chain navigation: Component -> Evidence -> Dependency -> Conflict -> Decision -> Readiness -> Audit -> Release.
- Deterministic repeated renders for identical inputs.
- Fail-closed rendering for schema/provenance violations.
