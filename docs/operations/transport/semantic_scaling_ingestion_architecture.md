# Semantic Scaling Ingestion Architecture

## Scope

`semantic_scaling_ingestion_engine.py` expands AURA ingestion from handcrafted
driver samples to recursive Linux audio-tree discovery with deterministic,
lineage-preserving artifact generation.
The current phase adds behavioral runtime semantics on top of structural
extraction.
The causality evolution phase extends this into runtime causal reasoning:

- causal event chains
- failure propagation and blast-radius analysis
- temporal replay causality and divergence detection
- runtime instability scoring
- preliminary root-cause inference

## Inputs

- Source root (real kernel tree)
- Discovery patterns:
  - `sound/soc/qcom/**/*.c`
  - `sound/soc/codecs/**/*.c`
  - `techpack/audio/**/*.c`
  - `include/sound/**/*.h`
- Prior cache state (`semantic_cache_state.json`) for incremental reuse

## Deterministic Processing

1. Recursive discovery with sorted path ordering.
2. Stable file hashing (`sha256`) and corpus fingerprinting.
3. Incremental invalidation:
   - changed files
   - removed files
   - header reverse-dependency invalidation
4. Async parsing with bounded workers (results normalized and sorted).
5. Typed graph generation with deterministic fingerprints.
6. Behavioral parsing for:
   - `snd_soc_dai_ops`
   - `snd_pcm_ops`
   - DAPM event-driven transitions
   - stream lifecycle callbacks (`open/startup/hw_params/prepare/trigger/...`)
   - runtime dependency tags (clock/regulator/pm/dsp/soundwire/mailbox/irq)

## Graph Outputs

- include dependency graph
- function call graph
- macro lineage graph
- DAPM route graph
- clock dependency graph
- control propagation graph
- subsystem ownership graph
- FE/BE DAI graph
- inter-driver dependency graph
- stream path relationships
- behavioral state graph
- activation order graph
- runtime causality graph
- power sequence graph
- causal event chain graph
- trigger dependency graph
- failure propagation graph

## Topology + Replay

- Topology model reconstruction from parsed widgets/routes.
- Replay simulation with transition logs and callback lifecycle transitions.
- DAPM behavioral model with activation timeline and power propagation edges.
- Stream intelligence report (conflicts/dead routes/missing clocks/invalid paths).
- Governance confidence report (semantic completeness + stability dimensions).
- Temporal causality report + runtime sequence fingerprint.
- Replay divergence report against prior deterministic sequence fingerprint.
- Root-cause inference report derived from observed failures.
- Mux conflict detection and invalid-state detection.
- Fail-closed when:
  - unknown widget references exist
  - topology cycle risk exists
  - stream conflict conditions are detected

## Governance

- Empty discovery is fail-closed (`no_eligible_source_files_discovered`).
- Runtime simulation/topology instability escalates fail-closed.
- Stream intelligence and confidence governance also fail-close promotion.
- Failure diagnostics are always persisted.

## Runner

`scripts/aura-semantic-scaling-ingestion.py` executes the engine and emits:

- canonical semantic artifacts (`semantic_*`)
- compatibility aliases for existing dashboards/pipelines:
  - `codec_graph.json`
  - `dapm_topology_graph.json`
  - `control_relationships.json`
  - `macro_dependencies.json`
  - `call_graph.json`
  - `stream_routing.json`
  - `subsystem_lineage.json`
  - `activation_timelines.json`
  - `state_transition_graph.json`
  - `power_propagation_graph.json`
  - `stream_intelligence_report.json`
  - `governance_confidence_report.json`

## Deterministic Replay Guarantees

- Stable fingerprints for graph/topology artifacts under unchanged inputs.
- Cache reuse ratio reported for incremental runs.
- Lineage ID derived from normalized source root + corpus fingerprint.
