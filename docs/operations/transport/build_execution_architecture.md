# Real Build Execution + Compilation Governance Architecture

## Mission

Provide governance-first real build cognition for Linux-style source trees.
This layer executes controlled build commands, reconstructs build topology and
symbol closure, computes confidence, and fail-closes on unresolved risk.

## Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/build_execution_engine.py`
- Runner:
  - `scripts/aura-build-execution.py`
- Persistence:
  - `BuildExecutionRegistry` with replay lineage

## Build Cognition Flow

1. ingest source root, patch context, governance state
2. run compile cognition as dependency-closure input
3. parse Makefiles and reconstruct object/source topology
4. execute controlled real build commands:
   - subsystem dry-run build
   - subsystem execution build
   - object dry-run build
   - object execution build
5. reconstruct symbol closure and cross-subsystem coupling
6. detect runtime-sensitive build regions and unsafe impacts
7. compute build confidence from command + closure + risk inputs
8. apply fail-closed governance decision
9. persist deterministic replay lineage and artifacts

## Safety Model

- sandbox output directory (`O=<tempdir>`) isolates build artifacts
- no source-tree mutation required for validation
- governance blocks promotion on unresolved risk conditions
- deterministic lineage persisted for command/dependency snapshots

## Fail-Closed Conditions

- unresolved symbol closure
- dependency graph inconsistencies
- confidence below threshold
- unsafe runtime-sensitive region impacts
- unsafe incremental rebuild outcomes
- linker/modpost instability markers
- incomplete replay lineage

## Generated Artifacts

- `build_topology_graph.json`
- `subsystem_build_map.json`
- `object_lineage_graph.json`
- `symbol_closure_report.json`
- `unresolved_dependency_report.json`
- `build_confidence_report.json`
- `runtime_sensitive_build_regions.json`
- `deterministic_build_replay.json`
- `build_execution_summary.json`
- `governance_build_decision.json`

