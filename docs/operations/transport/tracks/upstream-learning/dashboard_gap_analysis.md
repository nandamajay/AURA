# M9 Dashboard Gap Analysis (M8 Alignment)

## 1) M8 Artifact Field Coverage Matrix

### Coverage legend
- `Visualized`: field is explicitly rendered in a structured widget (table/card/chart)
- `Partially used`: field is indirectly available but not rendered as structured semantic data
- `Hidden`: field has no current dashboard binding

| Artifact | Dashboard ownership | Visualized fields | Partially used fields | Hidden fields | Lineage visibility | Evidence visibility | Readiness visibility |
|---|---|---:|---:|---|---|---|---|
| `track_b_equivalence_map.json` | None (no page/endpoint binding) | 0 | 0 | `artifact_name,schema_version,classification,stage_id,upstreaming_request,corpora,downstream_anchor,candidate_mappings,ranking_policy,lineage,evidence,fail_closed_reasons` | None | None | None |
| `track_b_dependency_matrix.json` | None | 0 | 0 | `artifact_name,schema_version,classification,stage_id,dependency_records,lineage,evidence,fail_closed_reasons` | None | None | None |
| `track_b_conflict_ledger.json` | None | 0 | 0 | `artifact_name,schema_version,classification,stage_id,conflicts,unresolved_conflict_count,resolved_conflict_count,resolution_policy,lineage,evidence,fail_closed_reasons` | None | None | None |
| `track_b_equivalence_decision.json` | None | 0 | 0 | `artifact_name,schema_version,classification,stage_id,decision_state,selected_candidate,mandatory_checks,complexity,lineage,evidence,fail_closed_reasons` | None | None | None |
| `track_b_upstreaming_report.json` | None | 0 | 0 | `artifact_name,schema_version,classification,stage_id,downstream_component,decision_state,upstream_equivalents,required_patches,risk_assessment,dependency_summary,architectural_differences,caller_callee_chain,lineage,evidence,fail_closed_reasons` | None | None | None |
| `track_b_upstreaming_readiness.json` | None | 0 | 0 | `artifact_name,schema_version,classification,stage_id,decision_state,readiness_status,mandatory_checks,lineage,evidence,fail_closed_reasons` | None | None | None |

## 2) Why Coverage Is Missing (Evidence-backed)

| Gap | Why missing | Impact | Severity | Priority |
|---|---|---|---|---|
| No M8 API surface | Core API routes expose runtime contracts, governance, memory, knowledge, tasks, etc., but no Track-B/M8 artifact endpoints. | Dashboard cannot query M8 artifacts. | CRITICAL | P0 |
| Runtime contracts are runtime-only | Runtime artifact type contract is limited to 5 runtime artifact types and corresponding files. | M8 artifacts are excluded from typed ingestion and runtime dashboards. | CRITICAL | P0 |
| Learning Center is memory-ledger only | Learning Center binds only memory summary/timeline/decisions/failures/replay incidents. | Track-B M8 outputs never appear in Learning Center. | CRITICAL | P0 |
| Evidence index root restrictions | Evidence index covers fixed sections (`evidence`, `docs/operations/transport`, etc.) but not default agent output root (`/data/outputs`) or `track_b_validation`. | Even raw-file browsing often misses generated Track-B outputs. | HIGH | P0 |
| Track-B artifacts are produced in agent output directories | Track-B executor writes M8 artifacts to per-task output directory; no auto-registration into dashboard-facing registry. | Artifacts exist but are operationally invisible. | HIGH | P0 |

## 3) Broken / Missing / Duplicated / Stale / Partial Paths

### Missing (functional)
- No dashboard page, card, widget, table, or chart consumes the six frozen M8 artifacts.
- No backend endpoint returns M8 artifact index/read/summary for dashboard consumption.
- No readiness view for M8 completion/readiness/blockers/conflicts/dependency/evidence/audit/release/learning coverage.

### Duplicated
- Duplicate route + nav entry for Approval Operations (`/approvals` and `/approval`).

### Stale / placeholder-connected
- Patch endpoints return empty/placeholder payloads (`patches=[]`, `status=not_found`, empty diff/evidence).

### Partially connected
- Debugging Center Evidence Browser can only show raw files from allowed evidence sections; it is not a semantic M8 viewer and has no M8 lineage drill-down.
- Architecture Lab and parts of Simulation Center use static in-code datasets, not runtime/evidence-backed M8 data.

## 4) Field-Level Gap-to-Fix Plan

| Uncovered field set | Implementation approach | Complexity | Priority |
|---|---|---|---|
| All M8 top-level required fields across 6 artifacts | Add Track-B artifact index/read core endpoints and typed dashboard adapters; render each required field in structured cards/tables (with schema validation badges). | M | P0 |
| All M8 `lineage` fields | Add lineage graph + lineage table widgets with forward/reverse links and source artifact SHA/path display. | M | P0 |
| All M8 `evidence` fields | Add evidence panel per artifact with evidence row drill-down, provenance field checks, and source artifact backlinks. | M | P0 |
| M8 readiness fields (`readiness_status`, `mandatory_checks`, `fail_closed_reasons`) | Add readiness dashboard cards + check matrix + blocker counters. | S | P0 |
| Conflict-specific fields (`conflicts`, counts, resolution policy) | Add conflict ledger widgets with unresolved/resolved partitions + filtering by conflict type. | S-M | P1 |
| Report richness fields (`caller_callee_chain`, `architectural_differences`, `required_patches`) | Add report diff/timeline panes and export views. | M | P1 |

## 5) Priority Assignments (P0/P1/P2)

### P0
- Add M8 backend artifact index/read endpoints.
- Add dashboard M8 route(s) and widgets for all six artifacts.
- Add readiness summary widgets.
- Add direct lineage/evidence drill-down for M8 artifacts.
- Add artifact registration/indexing from Track-B outputs into dashboard-visible index.

### P1
- Add conflict triage UX (sorting/filtering/aggregation).
- Add report-centric views (architectural differences/call-chain navigation).
- Remove approval route duplication (`/approval` alias deprecation plan).

### P2
- Replace static demo graphs (Architecture Lab / Simulation visuals) with evidence-backed feed variants.
- Add historical trends for M8 readiness evolution over runs.

## 6) Evidence Pointers
- Dashboard routing/nav: `AURA/dashboard/src/App.tsx`, `AURA/dashboard/src/components/Layout.tsx`
- API route map: `AURA/dashboard/src/config.ts`
- Learning Center endpoint bindings: `AURA/dashboard/src/pages/LearningCenter.tsx`
- Runtime contract scope: `AURA/dashboard/src/runtime/contracts.ts`, `AURA/services/core/src/core/contracts/transport_artifact_contracts.py`
- Runtime endpoints: `AURA/services/core/src/core/routers/runtime.py`
- Knowledge evidence section scope: `AURA/services/core/src/core/routers/knowledge.py`
- Patch placeholder behavior: `AURA/services/core/src/core/routers/patches.py`
- Track-B M8 artifact generation/output model: `AURA/agents/src/aura_agents/track_b_stage_execution.py`
- Agent output root: `AURA/services/core/src/core/services/agent_runtime.py`
