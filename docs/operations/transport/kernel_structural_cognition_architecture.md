# Kernel Structural Cognition Layer Architecture

## Scope

This layer ingests real downstream/upstream Linux kernel source trees and emits
replay-safe structural cognition artifacts for:

- driver registration/lifecycle understanding
- topology structure understanding (DTS, DAPM, FE/BE, SoundWire)
- runtime-to-source evidence correlation
- portability blocker analysis
- downstream-to-upstream equivalence tracing

Execution remains advisory/governed-only.

## Architecture Boundaries

Preserved constraints:

- fail-closed governance
- deterministic replay and deterministic artifact fingerprints
- runtime evidence is execution truth
- plugin isolation (target intelligence only through plugin adapter)
- no autonomous patching/topology rewriting/runtime mutation

Explicitly blocked:

- autonomous source mutation
- autonomous patch generation
- autonomous topology mutation
- unsafe runtime rewrite

## Core Components

- `aura_sdk.transport.kernel_structural_cognition`
  - `KernelStructuralCognitionPlanner`
  - `KernelStructuralCognitionRegistry`

- `scripts/aura-kernel-structural-cognition.py`
  - deterministic operational entrypoint

- plugin contract extension:
  - `structural_cognition_adapter`

## Structural Cognition Pipeline

1. Load governance/runtime evidence from cognition registry.
2. Load target plugin and resolve `structural_cognition_adapter` payload.
3. Parse downstream tree:
   - Kconfig symbols/includes
   - Makefile object linkage
   - DTS/DTSI nodes/includes/SoundWire markers
   - ALSA registration APIs
   - `snd_soc_component_driver` lifecycle callbacks
   - `snd_soc_ops` callback chains
   - DAPM widgets/routes
   - FE/BE DAI link candidates
   - vendor hooks/tokens
4. Build upstream index from focused paths (`sound/soc`, `include/sound`, `drivers/soundwire`, plugin hints).
5. Build upstream equivalence trace with confidence and path evidence.
6. Correlate runtime evidence to source-level structures.
7. Derive portability blocker graph and governance classification.
8. Emit deterministic structural graph set and replay trace.

## Generated Artifacts

Required outputs:

- `structural_graph.json`
- `driver_registration_graph.json`
- `topology_structure_graph.json`
- `runtime_source_correlation.json`
- `downstream_hook_inventory.json`
- `upstream_equivalence_trace.json`
- `portability_blocker_graph.json`
- `callback_chain_graph.json`
- `deterministic_structural_fingerprint.json`

Additional replay/ops outputs:

- `deterministic_structural_replay.json`
- `kernel_structural_cognition_summary.json`

## Determinism Model

Determinism is enforced by:

- stable sorting of parsed entities
- bounded artifact payload ordering
- stable fingerprints for each artifact
- aggregate structural fingerprint composed from artifact fingerprints
- lineage-indexed replay output with deterministic replay fingerprint

## Governance Model

- runtime truth precedence is explicit in correlation artifacts
- governance boundary report is embedded in structural fingerprint artifact
- any autonomous mutation flags trigger fail-closed classification
- portability blocker graph contributes to final structural classification

## Plugin Isolation Model

Core planner remains target-agnostic and must not branch on target identity.
All target-specific structural hints are sourced from:

- `plugin.structural_cognition_adapter(...)`

Adapter payload governs:

- scan bounds
- upstream focus paths
- equivalence hints
- blocker patterns

## Mission Impact

This layer improves AURA mission dimensions directly:

- driver understanding: registration, lifecycle, and callback-chain visibility
- topology understanding: FE/BE + DAPM + DTS/SoundWire structural graphs
- runtime evidence reasoning: runtime command/route correlation to source
- regression detection: structural fingerprint drift and blocker deltas
- deterministic replay: replay-safe lineage and deterministic fingerprints
- upstream conversion capability: confidence-scored equivalence trace + portability blockers
