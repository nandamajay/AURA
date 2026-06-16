# M9 Dashboard Widget Inventory (M8 Baseline)

## Scope
- Release tag: `m8-release-v1`
- Commit: `99c455dffd7418dd3e7053057eafbedd073ecffb`
- Audit basis: implemented dashboard + core routers only (no intended design assumptions)

## Navigation Inventory
| Route | Page Component | Nav Source | Notes |
|---|---|---|---|
| `/` | `GlobalCommandCenter` | `App.tsx` + `Layout.tsx` | Runtime operations snapshot |
| `/migration` | `DriverMigrationCenter` | `App.tsx` + `Layout.tsx` | Task submit/queue workflow |
| `/knowledge` | `KnowledgeGraphCenter` | `App.tsx` + `Layout.tsx` | Rules/evidence graph |
| `/maintainers` | `MaintainerIntelligenceCenter` | `App.tsx` + `Layout.tsx` | Memory-ledger intelligence |
| `/learning` | `LearningCenter` | `App.tsx` + `Layout.tsx` | Memory-ledger learning view |
| `/agents` | `LiveAgentObservability` | `App.tsx` + `Layout.tsx` | Agent runtime monitoring |
| `/architecture` | `ArchitectureLab` | `App.tsx` + `Layout.tsx` | Static dependency lab |
| `/patches` | `PatchReviewWarRoom` | `App.tsx` + `Layout.tsx` | Patch lifecycle view |
| `/debug` | `DebuggingCenter` | `App.tsx` + `Layout.tsx` | Replay + evidence explorer |
| `/simulation` | `SimulationControlCenter` | `App.tsx` + `Layout.tsx` | Simulation controls + static DAPM playback |
| `/approvals` | `ApprovalOperationsCenter` | `App.tsx` + `Layout.tsx` | Governance/charter actions |
| `/approval` | `ApprovalOperationsCenter` | `App.tsx` + `Layout.tsx` | Duplicate alias path |
| `/governance` | `GovernanceCommandCenter` | `App.tsx` + `Layout.tsx` | Governance timeline |
| `/runtime` | `RuntimeCognitionCenter` | `App.tsx` + `Layout.tsx` | Runtime contract dashboards |
| `/tasks` | `DriverMigrationCenter` | `App.tsx` compatibility route | Legacy alias |

## Global Layout Widgets
| Widget | Type | Backing Source |
|---|---|---|
| Sidebar nav (`NAV_ITEMS`) | Navigation | Static route map |
| Sticky header auth/login/logout | Form + status | `/api/v1/auth/*`, `/health/ready`, `/api/v1/agents/running` |
| Global search | Input -> route | Redirects to `/knowledge?q=` |
| Auth debug strip | Status strip | Auth store runtime state |
| Footer health strip | Status strip | Backend connectivity + running agent count |
| `ChatPanel` quick commands | Floating panel | `/health/ready`, `/api/v1/agents/running`, `/api/v1/tasks/queue/stats` |
| `TeachingOverlay` | Overlay | Static teaching flow data |

## Page Widget Inventory

### `/` Global Command Center
- Status tiles (8 metrics): Operational class, determinism class, queue pressure, replay health, retry activity, websocket/SSE, governance flow, last snapshot.
- Section cards:
  - `Operational Alert Surface`
  - `Coexistence Pressure Snapshot`
  - `Plugin / Domain Activity` (tabular domain totals)
  - `Operator Workflows` (quick links)
- Backing endpoint: `/health/runtime-overview`
- Backing artifacts/tables: task queue stats, task/replay/governance DB aggregates, WS coexistence metrics.

### `/migration` Driver Migration Center
- Section cards:
  - `Queue Snapshot`
  - `Engineering Workflow Tracker`
  - `Create Migration Task`
  - `Current Workflow Task Detail`
  - `Task List (Current API Response)`
- Backing endpoints: `/api/v1/tasks/*`, `/api/v1/agents`
- Backing artifacts: task queue state, task records.

### `/knowledge` Knowledge Graph Center
- Section cards:
  - `Search Knowledge`
  - `Export Knowledge`
  - `Knowledge Graph Visualization` (D3 force/radial graph)
  - `Selected Node`
  - `Selected Relationship`
- Backing endpoints: `/api/v1/knowledge/rules`, `/api/v1/knowledge/search`, `/api/v1/knowledge/export`, `/api/v1/knowledge/evidence/index`
- Backing artifacts/tables: `migration_rules`, `rules_fts`, allowed filesystem evidence sections.

### `/maintainers` Maintainer Intelligence Center
- `EndpointGridPage` panels:
  - Maintainer Intelligence
  - Known Risks
  - Technical Debt
  - Governance High-Risk Actions
  - Architecture Drift
- Backing endpoints: `/api/v1/memory/*`, `/api/v1/charter/high-risk-actions`

### `/learning` Learning Center
- `EndpointGridPage` panels:
  - Memory Summary
  - Learning Timeline
  - Decisions
  - Failures
  - Replay Incidents
- Backing endpoints: `/api/v1/memory/*`
- Backing artifacts/tables: memory ledgers + cross-ledger timeline query.

### `/agents` Live Agent Observability
- Section cards:
  - `Spawn Agent`
  - `Stream Status`
  - `Agent Grid`
  - `Focused Agent`
  - `Circuit Breakers`
  - `Runtime Pressure Surface`
  - `Per-Domain Coexistence Health`
  - `Recent Stream Events`
  - optional `Focused Events: <agent>`
- Charts/tables: progress bars, event feeds, per-domain health rows.
- Backing endpoints: `/api/v1/agents/*`, `/health/runtime-overview` + websocket stream.

### `/architecture` Architecture Lab
- Section cards:
  - `Dependency Graph Controls`
  - `Force-Directed Dependency Graph` (D3 graph)
  - `Legend`
  - `Selected Node Details`
- Backing source: hardcoded `DRIVER_GRAPHS` constant (no API).

### `/patches` Patch Review War Room
- Section cards:
  - `Patch Query`
  - `Patch List`
  - `Patch Detail`
  - `Patch Diff`
  - `Evidence`
- Backing endpoints: `/api/v1/patches/*`
- Current backend behavior: placeholder/empty payloads (`[]`, `not_found`, empty diff).

### `/debug` Debugging Center
- Section cards:
  - `Replay Boundary Inspection`
  - `Replay Failure / Non-Replayable Semantics`
  - `Replay Lifecycle Timeline`
  - `Replay Summary Payload`
  - `Replay Output`
  - `Determinism Inspector`
  - `Evidence Browser`
  - `Evidence File: <path>`
  - DataPanel trio: `Audit Ledger`, `Replay Incidents`, `Ops Incidents`
- Backing endpoints: `/api/v1/tasks/*/replay*`, `/api/v1/knowledge/evidence/*`, `/api/v1/memory/validation/nondeterminism-check`, governance/memory endpoints.

### `/simulation` Simulation Control Center
- Section cards:
  - `Start Simulation`
  - `Simulation Status`
  - `DAPM Simulation Visualization` (canvas)
  - `Available Scenarios`
- Backing endpoints: `/api/v1/simulation/*`
- Additional visualization source: hardcoded `DAPM_WIDGETS`, `DAPM_CONNECTIONS`, `DAPM_FRAMES`.

### `/approvals` and `/approval` Approval Operations Center
- Section cards:
  - `Governance Approval Action`
  - `Charter Approval Action`
  - DataPanels: Governance Evidence Summary, Governance Approvals, Charter Pending Approvals
  - `Action Result`
- Backing endpoints: `/api/v1/governance/*`, `/api/v1/charter/*`.

### `/governance` Governance Command Center
- Section cards:
  - `Policy Evaluation (Dry-Run)`
  - `Timeline Classification Summary`
  - `Audit Timeline`
  - DataPanels: Governance Evidence Summary, Governance Approvals, Charter Pending Approvals, Fail-Safe Report, Integrity Report
- Backing endpoints: `/api/v1/charter/*`, `/api/v1/governance/*`.

### `/runtime` Runtime Cognition Center
- Section cards:
  - `Runtime Governance Decision`
  - `Runtime Confidence Analysis`
  - `Runtime Equivalence Comparison` (table)
  - `Runtime Topology Graph` (SVG timeline graph)
  - `Replay Lineage Exploration` (artifact table)
- Backing endpoints: `/api/v1/runtime/*`
- Backing contracts: runtime-only transport artifact contract set.

## M8 Artifact Representation Check
Required M8 artifacts:
- `track_b_equivalence_map.json`
- `track_b_dependency_matrix.json`
- `track_b_conflict_ledger.json`
- `track_b_equivalence_decision.json`
- `track_b_upstreaming_report.json`
- `track_b_upstreaming_readiness.json`

Current widget-level representation: **none** (0 dedicated pages/cards/tables/charts consuming these artifacts).

## Evidence Pointers
- Dashboard routes/nav: `AURA/dashboard/src/App.tsx`, `AURA/dashboard/src/components/Layout.tsx`
- Endpoint registry: `AURA/dashboard/src/config.ts`
- Runtime-only contract typing: `AURA/dashboard/src/runtime/contracts.ts`
- Runtime-only backend artifact contracts: `AURA/services/core/src/core/contracts/transport_artifact_contracts.py`
- Runtime router scope: `AURA/services/core/src/core/routers/runtime.py`
- Knowledge evidence index/read scope: `AURA/services/core/src/core/routers/knowledge.py`
- Learning center implementation: `AURA/dashboard/src/pages/LearningCenter.tsx`
- Track-B M8 artifact generation: `AURA/agents/src/aura_agents/track_b_stage_execution.py`
