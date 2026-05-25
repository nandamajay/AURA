# AURA Dashboard Architecture Audit

Date: 2026-05-24  
Branch context: `stabilization/p1-runtime-reliability`  
Scope: Architecture/state audit only (no new module implementation)

## Audit Method
- Performed static code audit of frontend (`AURA/dashboard/src`) and backend APIs (`AURA/services/core/src/core`).
- Performed build/runtime/dependency/route validation commands.
- Performed artifact availability audit against `docs/operations/transport` and current evidence ingestion contracts.

## 1) Existing Frontend Structure

### Routes and pages
Source: `AURA/dashboard/src/App.tsx`
- `/` -> GlobalCommandCenter
- `/migration` -> DriverMigrationCenter
- `/knowledge` -> KnowledgeGraphCenter
- `/maintainers` -> MaintainerIntelligenceCenter
- `/learning` -> LearningCenter
- `/agents` -> LiveAgentObservability
- `/architecture` -> ArchitectureLab
- `/patches` -> PatchReviewWarRoom
- `/debug` -> DebuggingCenter
- `/simulation` -> SimulationControlCenter
- `/approvals` and `/approval` -> ApprovalOperationsCenter
- `/governance` -> GovernanceCommandCenter
- Back-compat route: `/tasks` -> DriverMigrationCenter

### Layout/auth/login flow
Source: `AURA/dashboard/src/components/Layout.tsx`
- Global sidebar + topbar layout (single shell around all routes).
- Inline login form in topbar; JWT token stored via Zustand auth store.
- Session persistence in `localStorage` (`aura.dashboard.session`).
- No route-level guard/redirect; pages still render while unauthenticated (API calls then fail with 401).
- Global connectivity poll every 15s (`/health/ready`, `/agents/running`).

### Components
- Reusable primitives: `PagePrimitives.tsx`
- Generic JSON endpoint panels: `DataPanel.tsx`, `EndpointGridPage.tsx`
- Shell utilities: `ChatPanel.tsx`, `TeachingOverlay.tsx`

### Graph systems/layout systems
- D3 force/radial graph: `KnowledgeGraphCenter.tsx`
- D3 dependency graph: `ArchitectureLab.tsx`
- Canvas timeline/playback: `SimulationControlCenter.tsx`
- Timeline/event rendering: `GovernanceCommandCenter.tsx`, `DebuggingCenter.tsx`

### State management
- Global state: only auth/session via Zustand (`useAuthStore.ts`).
- All other page data state is page-local `useState` + `useApiData` polling.
- No centralized data cache/query invalidation layer.

### API integration
- Central API constants: `config.ts`
- Generic fetch wrapper: `api/client.ts`
- Generic polling hook: `useApiData.ts`
- Integration style is endpoint-driven JSON rendering + ad-hoc page orchestration.

### Artifact loading system (frontend)
- Evidence index/read UX in `DebuggingCenter.tsx` via:
  - `/api/v1/knowledge/evidence/index`
  - `/api/v1/knowledge/evidence/read`
- Artifact consumption is generic text/JSON preview, not typed artifact adapters.

## 2) Existing Backend / Dashboard APIs

### FastAPI app and routers
Source: `AURA/services/core/src/core/main.py`
- Routers mounted for: `health`, `auth`, `agents`, `tasks`, `patches`, `knowledge`, `governance`, `engineering`, `simulation`, `memory`, `charter`, `provenance`.
- Dashboard currently consumes primarily: health/auth/agents/tasks/patches/knowledge/governance/memory/simulation/charter.

### JSON ingestion / artifact loaders
Source: `AURA/services/core/src/core/routers/knowledge.py`
- Evidence file browser endpoints:
  - `GET /api/v1/knowledge/evidence/index`
  - `GET /api/v1/knowledge/evidence/read`
- Allowed sections currently mapped to:
  - `evidence/`
  - `docs/architecture-consolidation/`
  - `p1/`, `p2/`, `phase0/`
- `docs/operations/transport/` is **not** in section mapping.

### Replay registry readers / governance readers
- Replay readers:
  - `GET /api/v1/tasks/{task_id}/replay`
  - `GET /api/v1/tasks/{task_id}/replay/state`
- Governance readers:
  - `GET /api/v1/governance/approvals`
  - `GET /api/v1/governance/audit`
  - `POST /api/v1/governance/approvals/{approval_id}`

### Graph adapters
- No dedicated backend graph endpoints for runtime truth/topology/governed conversion artifacts.
- Graph UIs currently build graphs on frontend from generic API payloads or static data.

## 3) Existing Visualization Capabilities

### Implemented
- Rule/evidence D3 knowledge graph (interactive node/link inspection, force/radial).
- Governance timeline filtering and continuity checks.
- Replay timeline reconstruction UI + evidence file browser.
- Agent live observability dashboard (REST + websocket stream).
- DAPM playback canvas animation (simulation-like visualization).

### Not yet mature
- Runtime topology visualization for real artifacts is not first-class.
- Replay visualization is task-log oriented, not runtime-equivalence artifact oriented.
- Governance rendering exists but is mostly ledger/event list + raw JSON.
- Most panels still present raw JSON rather than domain-specific visual models.

## 4) Existing Dashboard Functionality Audit

### Working modules
- GlobalCommandCenter
- DriverMigrationCenter
- KnowledgeGraphCenter
- LiveAgentObservability
- DebuggingCenter
- GovernanceCommandCenter
- ApprovalOperationsCenter
- LearningCenter / MaintainerIntelligenceCenter (endpoint grid style)

### Incomplete / placeholder modules
- PatchReviewWarRoom: backend patch endpoints exist but return mostly placeholders (empty list/diff/evidence, `status: not_found`).
- ArchitectureLab: dependency graph content is static embedded sample graph, not backed by live source-tree cognition artifacts.
- SimulationControlCenter: simulation backend exists but results are deterministic synthetic scoring; DAPM canvas path playback is static hardcoded widget graph.

### Broken/at-risk modules
- Backend runtime startup in current environment is blocked (see validation section), so all authenticated dashboard modules are runtime-blocked outside a correct Python 3.12 + dependency environment.
- Artifact-driven runtime cognition views are not directly wired to `docs/operations/transport` outputs.

### Duplicated logic
- Repeated polling + JSON card patterns across many pages without typed shared domain adapters.
- Similar approval/governance views duplicated across GovernanceCommandCenter and ApprovalOperationsCenter (different forms over similar data).
- Route aliases `/approvals` and `/approval` intentionally duplicate same page.

### Missing architecture areas
- No typed runtime artifact schema registry in frontend.
- No dedicated runtime-equivalence/governance decision visual modules.
- No normalized backend API facade specifically for dashboard runtime cognition artifacts.

## 5) Build/Runtime Validation

### Frontend build validation
Command:
- `cd AURA/dashboard && npm run build`
Result:
- PASS (`tsc` + `vite build` succeeded)

### Frontend dependency validation
Command:
- `cd AURA/dashboard && npm ls --depth=0`
Result:
- PASS (installed dependency tree resolved)

### Backend dependency validation
Commands:
- `python -m pip check` -> PASS (global environment consistency)
- Import probe for required runtime libs -> PARTIAL/FAIL for service needs:
  - Missing: `uvicorn`, `jose`, `passlib`

### Backend startup validation
Commands:
- `PYTHONPATH=... python -m uvicorn core.main:app ...` -> FAIL (`No module named uvicorn`)
- `PYTHONPATH=... python -m pytest -q` -> FAIL during collection due Python version mismatch (`StrEnum` import; project requires Python >=3.12)

### Route validation
- Frontend endpoint keys used by pages map to existing backend route families.
- Dynamic charter action route (`/charter/approvals/{id}/{approve|reject}`) is valid by constrained UI options.
- Patch routes exist but functional payloads are placeholders.
- `metrics` endpoint exists in backend (`/metrics`) but is unused in current UI flows.

## 6) Technical Debt Analysis

### Architectural inconsistencies
- Mixed maturity model: advanced D3/canvas views coexist with raw JSON endpoint cards.
- Runtime cognition artifacts are generated in `docs/operations/transport` but dashboard artifact reader points elsewhere.
- No clear typed contract layer between backend artifact producers and frontend visualization consumers.

### Broken contracts
- Patch review UI expects meaningful patch data; backend patch router currently stubbed.
- ArchitectureLab implies real dependency cognition but serves static demo graph.

### Missing normalization
- Event/artifact payloads rendered as raw JSON in many surfaces.
- No shared type normalization for replay/governance/runtime artifact schemas.

### Scalability/performance risks
- Heavy polling on multiple pages (10–30s) without shared query cache/dedupe.
- Large JSON serialization (`JSON.stringify`) rendered directly in DOM cards.
- Evidence index scans filesystem recursively per request (can be expensive with large trees).
- D3 layouts rerun fully on data changes; no progressive rendering strategy.

## 7) Artifact Integration Audit (Required Files)

Target files in `docs/operations/transport`:
- `runtime_equivalence_report.json` -> exists
- `hardware_truth_graph.json` -> exists
- `replay_consistency_report.json` -> exists
- `runtime_governance_decision.json` -> exists
- `transformation_confidence_report.json` -> exists

Current dashboard support status:
- File existence: YES
- First-class typed dashboard modules: NO
- Indirect readable via current evidence API: NO (section mapping does not include `docs/operations/transport`)
- Net: **Not currently integrated into dashboard runtime workflows.**

## 8) Visualization Maturity Assessment

Scale: 1 (low) to 5 (high)
- Governance visibility: **3/5** (timeline + approvals available, but mostly ledger/raw JSON)
- Replay visibility: **3/5** (task replay timeline and evidence browser exist)
- Runtime topology visibility: **2/5** (mostly static/synthetic visuals)
- Explainability maturity: **2/5** (some reasoning context; no typed causality/explainability model)
- Observability maturity: **3/5** (live agent WS + runtime overview available; artifact fusion still missing)

## 9) UX Audit

### Enterprise readiness
- Moderate: structured navigation, stable shell, role/session support present.
- Gaps: many panels are operator-facing raw JSON; limited domain-specific workflows for runtime cognition artifacts.

### Readability
- Good baseline readability for tables/cards/timelines.
- Complex raw JSON blocks reduce signal-to-noise for incident workflows.

### Debugging usefulness
- Good for task replay/audit browsing.
- Limited for runtime-equivalence and hardware-truth investigation due missing first-class visualization.

### Governance clarity
- Governance controls visible and explicit.
- Promotion/risk context lacks unified runtime-evidence decision dashboard.

### Operational usability
- Usable for current orchestration and monitoring basics.
- Not yet optimized for high-volume runtime artifact triage.

---

## CURRENT STATE
Dashboard is a functional operations console with mixed maturity: strong shell/routing/auth basics, working governance/replay/task observability flows, but runtime-cognition artifact integration is still generic/indirect and partially blocked by backend environment prerequisites.

## WHAT IS WORKING
- Frontend build and dependency resolution.
- Core route/page shell, auth/session handling, polling infrastructure.
- Governance timeline + approval controls.
- Replay explorer + evidence browser for configured evidence sections.
- Live agent observability (REST + websocket model).
- Knowledge graph rendering from rule/evidence API payloads.

## WHAT IS MISSING
- First-class dashboard modules for runtime cognition outputs in `docs/operations/transport`.
- Direct artifact loader support for `docs/operations/transport` section.
- Typed runtime topology/equivalence/governance visualization contracts.
- Real backend patch lifecycle data for PatchReviewWarRoom.
- Environment-complete backend runtime validation path in current machine (Python 3.12 + auth/runtime deps).

## WHAT SHOULD BE REFACTORED
- Introduce typed artifact adapter layer (frontend + backend) instead of raw `JsonBlock` dependency.
- Consolidate repeated endpoint polling patterns and dedupe fetch cycles.
- Split static/demo visualization data from production runtime artifact visualizations.
- Normalize governance/replay/runtime schema mapping through shared contracts.

## WHAT SHOULD BE IMPLEMENTED NEXT
1. Backend evidence section extension to include `docs/operations/transport` as a governed read-only section.
2. Typed runtime artifact API façade (runtime equivalence, hardware truth graph, replay consistency, runtime governance decision, transformation confidence).
3. Dedicated runtime cognition dashboard modules consuming typed contracts.
4. Patch router completion to replace placeholder responses with real patch lineage data.
5. Query/state orchestration layer for caching, polling dedupe, and large artifact pagination.

## RECOMMENDED IMPLEMENTATION ORDER
1. **Contract foundation**: add transport artifact section + typed backend DTO endpoints.
2. **Integration bridge**: frontend artifact data service + schema normalization + error classification.
3. **Critical views**: runtime governance decision panel, runtime divergence/equivalence dashboard, hardware truth topology view.
4. **Correlation views**: replay consistency + transformation confidence cross-linking.
5. **Patch workflow hardening**: patch router implementation + PatchReviewWarRoom upgrade.
6. **Performance hardening**: shared query cache, evidence indexing optimization, large JSON virtualization.

## Dashboard Maturity Summary
Current maturity: **Foundational-to-Intermediate (about 2.8/5)**. Operations and governance basics are usable; runtime cognition visibility is not yet production-grade.

## Blockers Summary
- Backend runtime environment mismatch (Python 3.10 vs required >=3.12).
- Missing runtime dependencies (`uvicorn`, `python-jose`, `passlib`) in current environment.
- Patch router placeholder implementation.
- No direct transport artifact ingestion path for runtime cognition outputs.

## Architectural Risk Summary
- Contract drift risk between artifact producers and UI consumers.
- Increasing maintenance cost from duplicated endpoint-card patterns.
- Performance risk from recursive evidence scanning + repeated polling + raw JSON rendering.
- Misleading confidence risk when static demo graphs coexist with real-runtime dashboards without explicit separation.

## Recommended Next Phase
**Phase: Runtime Cognition Dashboard Integration (Contract-First).**
- Do not add broad new modules first.
- First establish backend transport artifact contracts + section exposure + typed normalization.
- Then implement focused runtime governance/topology/equivalence views on top of those contracts.
