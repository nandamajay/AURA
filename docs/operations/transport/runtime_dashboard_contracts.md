# Runtime Dashboard Contracts

## Scope
Contract-first runtime cognition integration between `aura-core` runtime APIs and the dashboard runtime workflow views.

## Backend Contract Source
- Module: `AURA/services/core/src/core/contracts/transport_artifact_contracts.py`
- Contract artifacts:
  - `runtime_equivalence_report.json`
  - `hardware_truth_graph.json`
  - `replay_consistency_report.json`
  - `runtime_governance_decision.json`
  - `transformation_confidence_report.json`

## Runtime API Surface
- `GET /api/v1/runtime/artifacts/index`
- `GET /api/v1/runtime/artifacts/read`
- `GET /api/v1/runtime/governance/summary`
- `GET /api/v1/runtime/topology`
- `GET /api/v1/runtime/equivalence`
- `GET /api/v1/runtime/confidence`

## Frontend Typed Contracts
- Module: `AURA/dashboard/src/runtime/contracts.ts`
- Core interfaces:
  - `RuntimeArtifactMetadata`
  - `ContractValidation`
  - `RuntimeArtifactsIndexResponse`
  - `RuntimeGovernanceSummaryResponse`
  - `RuntimeTopologyResponse`
  - `RuntimeEquivalenceResponse`
  - `RuntimeConfidenceResponse`

## Normalization + Adapter Layer
- Module: `AURA/dashboard/src/runtime/adapters.ts`
- Responsibilities:
  - issue classification (`errors`/`warnings`)
  - governance tone mapping
  - confidence normalization (% view)
  - equivalence risk table normalization
  - runtime topology edge extraction from typed events

## Shared Runtime Query Layer
- Module: `AURA/dashboard/src/runtime/useRuntimeQuery.ts`
- Behavior:
  - cached query reads (TTL-based)
  - polling with deduplicated fetches
  - centralized runtime error handling per endpoint

## Runtime Cognition View
- Page: `AURA/dashboard/src/pages/RuntimeCognitionCenter.tsx`
- Route: `/runtime`
- Visual modules:
  - runtime governance decision indicator
  - runtime confidence analysis with threshold marker
  - runtime equivalence dimension table with critical risk highlighting
  - runtime topology graph (contract-driven FE/BE edge rendering)
  - replay lineage exploration table

## Governance/Replay Guarantees Preserved
- Advisory-only rendering (no runtime mutations)
- FAIL_CLOSED visibility retained from backend contract classification
- Runtime truth precedence retained (`runtime_truth_precedence` exposed in metadata)
- Replay lineage surfaces (`lineage_id`, `session_id`, `replay_fingerprint`) are first-class UI fields

## Deliberate Non-Changes
- No new simulation engine
- No synthetic runtime graph data
- No architectural redesign of existing shell/navigation
- Existing modules preserved
