# Real Downstream Ingestion Cognition Architecture

## Objective

Implement real downstream kernel ingestion cognition that remains:

- deterministic
- replayable
- plugin-driven
- governance-safe
- fail-closed
- advisory only (no autonomous source mutation)

This phase improves mission outcomes by tying real source evidence to conversion planning:

- driver understanding
- topology understanding
- runtime evidence reasoning
- regression detection
- deterministic replay
- upstream conversion capability

## End-to-End Flow

1. Plugin adapter negotiation
- Runtime loads target plugin through `TargetPluginLoader`.
- Plugin provides:
  - `downstream_ingestion_adapter`
  - `upstream_match_adapter`
  - `topology_reconstruction_adapter`

2. Real downstream ingestion
- Engine: `downstream_driver_ingestion.py`
- Scans downstream kernel tree and extracts:
  - `snd_soc_ops` structures
  - `snd_soc_dai_link` FE/BE candidates
  - PCM/DPCM path literals
  - routing structures (`snd_soc_dapm_route`)
  - vendor extensions
  - proprietary runtime hooks
  - dependency markers (clock/regulator/gpio/soundwire)
  - timing dependency markers

3. Topology reconstruction
- Engine: `topology_reconstruction_cognition.py`
- Builds normalized portable topology graph:
  - FE nodes
  - BE nodes
  - inferred FE->BE route edges
  - mixer dependency abstractions
  - runtime activation order

4. Upstream semantic matching
- Engine: `upstream_semantic_matcher.py`
- Correlates downstream constructs against upstream tree tokens/scopes.
- Produces confidence-scored `EXACT` / `PARTIAL` / `UNRESOLVED` mappings.

5. Portability blocker classification
- Engine: `portability_blocker_classifier.py`
- Detects and classifies blockers:
  - downstream-only APIs
  - vendor-private abstractions
  - unsupported runtime assumptions
  - timing dependencies
  - replay compatibility gaps
  - governance violations
- Classification bins:
  - `replay_safe`
  - `advisory_only`
  - `blocked_unsafe`

6. Governance-safe conversion planning
- Engine: `real_downstream_conversion_planner.py`
- Produces deterministic migration advisory outputs only:
  - suggested upstream abstractions
  - staged conversion phases
  - topology equivalence reasoning
  - replay compatibility analysis
  - regression risk analysis
- Explicitly blocks autonomous patching/mutation.

7. Replay-safe persistence
- Registry class: `RealDownstreamConversionRegistry`
- Stores artifact paths and lineage in cognition registry.
- Generates deterministic replay trace from persisted lineage state.

## Generated Artifacts

- `downstream_driver_graph.json`
- `topology_runtime_graph.json`
- `upstream_equivalence_map.json`
- `portability_blockers.json`
- `migration_risk_report.json`
- `deterministic_conversion_plan.json`
- `governance_conversion_boundaries.json`
- `deterministic_conversion_replay.json`
- `real_downstream_ingestion_summary.json`

## Governance Boundaries

Allowed actions:
- analyze
- classify
- correlate
- fingerprint
- plan
- recommend
- replay

Forbidden actions:
- autonomous patch generation
- autonomous topology mutation
- unsafe runtime rewrite
- unsupported semantic assumptions

Execution posture:
- fail-closed on high-severity blockers or governance violations
- advisory-only planning output even when confidence is high

## Plugin Isolation Contract

Core planner never branches on explicit targets.
All target intelligence is provided via plugin adapters.

New contract methods:
- `downstream_ingestion_adapter`
- `upstream_match_adapter`
- `topology_reconstruction_adapter`

## Determinism and Lineage

- Every artifact includes deterministic fingerprints.
- Bundle fingerprint is computed from artifacts + governance boundaries.
- Replay fingerprint is derived from persisted lineage and artifact index.
- Registry history allows deterministic reconstruction without chat/session context.

## Validation Surface

Primary tests:
- `test_real_downstream_ingestion_static.py`
- `test_target_plugin_runtime_static.py`
- `test_portable_runtime_stabilization_static.py`
- `test_translation_intelligence_static.py`

Coverage includes:
- downstream parser validation (real sample tree when present)
- topology reconstruction validation
- semantic matching validation
- replay compatibility determinism
- governance boundary fail-closed handling
- plugin isolation checks
