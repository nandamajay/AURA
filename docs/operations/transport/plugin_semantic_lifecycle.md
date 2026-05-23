# Plugin Semantic Lifecycle

## Purpose
Define deterministic, replay-safe semantic cognition adapter execution inside plugin boundaries.

## Semantic Lifecycle Steps
1. `semantic_prepare`: validate adapter availability on selected plugin.
2. `semantic_collect`: collect DTS/topology/vendor/subsystem semantic evidence.
3. `semantic_classify`: compute deterministic semantic categories.
4. `semantic_persist`: persist semantic artifacts + lineage into cognition registry.
5. `semantic_replay_restore`: reproduce semantic outputs from persisted lineage.

## Adapter Contract
Each target plugin must provide:
- `dts_adapter`
- `topology_adapter`
- `vendor_api_adapter`
- `subsystem_descriptor_provider`
- `runtime_evidence_adapter`
- `topology_evidence_adapter`
- `semantic_evidence_adapter`
- `downstream_upstream_adapter`
- `topology_translation_adapter`
- `runtime_conversion_adapter`

## Safety Constraints
- Core runtime remains target-agnostic.
- Semantic parsing is plugin-driven only.
- Replay semantics are deterministic and evidence-backed.
- Any semantic adapter failure is fail-closed and quarantine-safe.
- Correlation fusion consumes adapter outputs and never bypasses plugin isolation.
- Translation planner consumes conversion adapters and never bypasses plugin isolation.
