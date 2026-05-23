# Kernel Semantic Subsystem Documentation

## Overview

The semantic subsystem transforms curated kernel audio knowledge HTML into deterministic, governed, machine-readable cognition artifacts.

It is designed for advisory reasoning support and never for direct runtime control.

## Public Modules and Contracts

1. `semantic_html_parser.py`
- API: `parse_semantic_html(source_path, source_id, source_version)`
- Contract:
  - deterministic section extraction
  - source hash capture
  - no execution side effects

2. `semantic_entity_extractor.py`
- API: `extract_semantic_entities(source_id, source_version, parsed_document, adapter_payload)`
- Entity families extracted:
  - ALSA entities
  - ASoC entities
  - FE/BE topology concepts
  - DPCM concepts
  - DAPM graph semantics
  - PCM lifecycle semantics
  - SoundWire concepts
  - Qualcomm downstream abstractions
  - upstream equivalence mappings
  - runtime lifecycle relationships
  - known portability blockers
  - migration equivalence rules
  - vendor workaround patterns
  - kernel subsystem vocabulary graph

3. `semantic_relationship_graph.py`
- API: `build_semantic_relationship_map(...)`
- Builds deterministic semantic co-occurrence links and domain relation typing.

4. `semantic_ontology_builder.py`
- API: `build_semantic_ontology(...)`
- Produces ontology classes, instances, predicates, and governance semantic rules.

5. `semantic_governance_boundary.py`
- API: `evaluate_semantic_governance_boundary(governance_state, requested_actions)`
- Enforces advisory-only posture and fail-closed behavior.

6. `semantic_equivalence_mapper.py`
- API: `build_semantic_equivalence_map(...)`
- Builds downstream->upstream semantic mapping with confidence.

7. `semantic_portability_reasoning.py`
- API: `build_semantic_portability_rules(...)`
- Classifies replay-safe/advisory/blocked transformation semantics.

8. `semantic_runtime_advisory.py`
- API:
  - engine: `SemanticRuntimeAdvisoryEngine`
  - method: `analyze(...)`
- Uses plugin adapter: `semantic_knowledge_adapter`
- Explicitly blocks runtime mutation and direct runtime execution.

9. `semantic_replay_compatibility.py`
- API: `build_semantic_replay_compatibility(...)`
- Validates deterministic artifact replay support.

10. `semantic_confidence_engine.py`
- API: `build_semantic_confidence_report(...)`
- Computes advisory confidence from deterministic factors.

11. `semantic_traceability_engine.py`
- APIs:
  - `build_semantic_traceability_graph(...)`
  - `KernelSemanticKnowledgeRegistry.persist(...)`
  - `KernelSemanticKnowledgeRegistry.replay(...)`
- Handles lineage history and deterministic replay trace generation.

## Plugin Adapter Contract

Required semantic adapter method:

- `semantic_knowledge_adapter(payload)`

Adapter responsibilities:

- taxonomy overrides
- equivalence confidence hints
- target-specific portability blocker patterns
- no runtime mutation behavior

## Runtime Safety Contract

Hard guarantees:

- `advisory_only == true`
- `runtime_state_mutation_allowed == false`
- `runtime_execution_permitted_from_semantics == false`

Any governance policy violation yields `FAIL_CLOSED`.

## Versioning and Traceability

Per-run bundle includes:

- source ID/version/path/hash
- lineage ID
- semantic knowledge fingerprint
- artifact fingerprints
- evidence references

Registry persistence keys:

- `kernel_semantic_knowledge_layer.latest`
- `kernel_semantic_knowledge_layer.history[]`
- `cognition_lineage[]`

## Deterministic Replay

Replay reconstruction is derived from persisted lineage and artifact index only.

No chat history is required.

Replay output:

- `semantic_knowledge_replay_trace.json`

## Validation Matrix

Validation objectives covered:

- deterministic outputs
- replay compatibility
- governance boundary enforcement
- no runtime mutation paths
- no autonomous execution
- plugin isolation maintained
- advisory-only reasoning preserved

Reference tests:

- `workspace/aura-sdk/tests/test_kernel_semantic_knowledge_layer_static.py`
- `workspace/aura-sdk/tests/test_target_plugin_runtime_static.py`
- `workspace/aura-sdk/tests/test_portable_runtime_stabilization_static.py`
