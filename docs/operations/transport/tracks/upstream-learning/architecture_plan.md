# Track B Architecture Plan (Discovery-Only Control Plane)

## Purpose
Track B introduces a controlled, breadth-first upstream learning flow for already-upstreamed Qualcomm audio ecosystems while keeping AURA core principles intact:
- evidence over assumptions
- deterministic artifacts
- fail-closed governance
- shared ontology, governance, confidence, and registry

Track B is discovery-only. It does not generate patches, convert drivers, or issue upstream readiness certification.

## Hard Constraints
- Reuse shared ontology. No duplicate ontology systems.
- Reuse shared governance. No duplicate governance systems.
- Reuse shared confidence model. No duplicate confidence systems.
- Reuse shared registry and lineage model. No duplicate registries.
- Reuse existing dashboard system. No separate dashboard.
- Preserve Runtime Track authority for runtime certification and replay integrity.

## Reused Shared Infrastructure (Authoritative)
- Ontology: `/local/mnt/workspace/AURA_V1/docs/operations/transport/semantic_ontology.json`
- Governance: `/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_governance_state.json`
- Cognition registry: `/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json`
- Confidence mapping: `/local/mnt/workspace/AURA_V1/docs/operations/transport/confidence_signal_mapping.json`
- Dashboard routes: `/local/mnt/workspace/AURA_V1/AURA/dashboard/src/App.tsx`

## Track B Lifecycle
```
DISCOVERED
  ↓
INDEXED
  ↓
STATIC_ANALYZED
  ↓
HISTORY_ANALYZED
  ↓
DTS_ANALYZED
  ↓
YAML_ANALYZED
  ↓
KCONFIG_ANALYZED
  ↓
MAKEFILE_ANALYZED
  ↓
RUNTIME_CORRELATED
  ↓
SEMANTIC_MODEL_BUILT
  ↓
UPSTREAM_PATTERN_EXTRACTED
  ↓
CROSS_PLATFORM_VALIDATED
  ↓
CERTIFIED_UNDERSTOOD_ADVISORY
```

## Stage Meanings
- `DISCOVERED`: candidate subsystem scope and sources are declared.
- `INDEXED`: source inventory and corpus boundaries are indexed.
- `STATIC_ANALYZED`: static structure (drivers, DTS, YAML, Kconfig, Makefile) is parsed.
- `HISTORY_ANALYZED`: review history and maintainer feedback patterns are collected.
- `DTS_ANALYZED`: DTS/DTSI topology semantics are extracted.
- `YAML_ANALYZED`: binding/schema semantics are extracted.
- `KCONFIG_ANALYZED`: compile-time feature semantics are extracted.
- `MAKEFILE_ANALYZED`: build integration semantics are extracted.
- `RUNTIME_CORRELATED`: static learning signals are correlated to Track A runtime truth artifacts.
- `SEMANTIC_MODEL_BUILT`: shared ontology-aligned semantic model is assembled.
- `UPSTREAM_PATTERN_EXTRACTED`: reusable framework and review patterns are identified.
- `CROSS_PLATFORM_VALIDATED`: each extracted pattern must be observed across multiple already-upstreamed Qualcomm platforms and shown to be reusable rather than board-specific.
- `CERTIFIED_UNDERSTOOD_ADVISORY`: advisory understanding is certified for learning progress only, not for code generation or submission readiness.

## Governance Model for Track B
- Fail-closed if required evidence is missing at any stage.
- Fail-closed if a stage attempts patch generation, conversion, or delivery authorization.
- Fail-closed if Track B tries to mutate runtime certification logic.
- Advisory-only outputs are mandatory for Track B completion states.

## Minimum Viable Track B Control Plane Assets
- `architecture_plan.md`
- `track_boundary_report.json`
- `learning_progress_model.json`
- `readiness_assessment.json`

No other systems are introduced in this MVP.
