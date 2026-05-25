# Stabilization Checkpoint

Generated: 2026-05-24T14:14:57.525421+00:00

## SCM
- Branch: stabilization/p1-runtime-reliability
- HEAD: 57bb94d12b32216e51b15049123ccbd26e4f7cbb

## Runtime Services
```
aura-core Up 14 minutes (healthy)
aura-llm-gateway Up 5 days (healthy)
aura-dashboard Up 5 days
aura-ws-server Up 5 days (healthy)
akdw Up 2 weeks (healthy)
patchwise-web Up 13 days
patchwise_app Up 3 weeks (healthy)
q-build-manager-web-1876 Up 4 weeks
q-build-manager-web-1835 Up 4 weeks
eloquent_elgamal Up 4 weeks
zen_shockley Up 5 weeks
```

## Validation Executed
- Dashboard build: `npm run build` (PASS)
- Backend tests (containerized Python 3.12): 11 passed
  - `test_runtime_contracts_static.py`
  - `test_runtime_endpoint_stabilization.py`
  - `test_operational_interface_endpoints.py`
- Runtime endpoint probes: all required runtime + evidence endpoints returned HTTP 200

## Runtime Core Health
- aura-core Up 14 minutes (healthy)

## Governance Snapshot
- classification: FAIL_CLOSED
- promotion_eligible: False
- runtime_confidence: 0.16

## Working Tree Note
Checkpoint created in pre-existing dirty worktree with out-of-scope files present.
```
M AURA/dashboard/src/App.tsx
 M AURA/dashboard/src/api/client.ts
 M AURA/dashboard/src/components/ChatPanel.tsx
 M AURA/dashboard/src/components/DataPanel.tsx
 M AURA/dashboard/src/components/Layout.tsx
 M AURA/dashboard/src/config.ts
 M AURA/dashboard/src/pages/DebuggingCenter.tsx
 M AURA/dashboard/src/pages/GlobalCommandCenter.tsx
 M AURA/dashboard/src/pages/GovernanceCommandCenter.tsx
 M AURA/dashboard/src/pages/KnowledgeGraphCenter.tsx
 M AURA/dashboard/src/pages/LiveAgentObservability.tsx
 M AURA/dashboard/src/store/useAuthStore.ts
 M AURA/services/core/src/core/lifespan.py
 M AURA/services/core/src/core/main.py
 M AURA/services/core/src/core/routers/knowledge.py
 M docs/operations/transport/stabilization_checkpoint.md
?? AURA/dashboard/src/pages/RuntimeCognitionCenter.tsx
?? AURA/dashboard/src/runtime/adapters.ts
?? AURA/dashboard/src/runtime/contracts.ts
?? AURA/evidence/
?? AURA/services/core/src/core/contracts/
?? AURA/services/core/src/core/routers/runtime.py
?? AURA/services/core/tests/test_runtime_contracts_static.py
?? AURA/services/core/tests/test_runtime_endpoint_stabilization.py
?? dashboard_architecture_audit.md
?? docs/operations/transport/_stabilization_probe_raw.json
?? docs/operations/transport/auth_integrity_report.json
?? docs/operations/transport/knowledge_graph_activation_report.md
?? docs/operations/transport/live_agent_observability_report.md
?? docs/operations/transport/runtime_api_contracts.json
?? docs/operations/transport/runtime_contract_integration_summary.md
?? docs/operations/transport/runtime_dashboard_contracts.md
?? docs/operations/transport/runtime_dashboard_readiness_report.md
?? docs/operations/transport/runtime_endpoint_validation.json
?? docs/operations/transport/runtime_integration_validation_report.json
?? docs/operations/transport/runtime_stabilization_report.md
?? evidence/compile_closure_wcd937x_20260520_003256/
?? evidence/compile_closure_wcd937x_continuation_20260520_033221/
?? evidence/dashboard/
?? evidence/provenance/
?? evidence/runtime_observability_tier1_20260520_045158/
?? evidence/runtime_observability_tier1_20260520_045254/
?? evidence/snapshot-runtime/
?? evidence/wcd937x_patchgen_20260519_194926/
?? evidence/wcd937x_real_study_20260519_062557/
?? evidence/wcd937x_study_20260519_101103/
```
