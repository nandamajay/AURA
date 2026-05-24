# Kernel Dependency Closure + Compile Cognition Architecture

## Mission Scope

This layer hardens AURA compile reasoning beyond syntax-level checks by
building deterministic dependency-closure cognition for governed
downstream-to-upstream transformations.

The layer is advisory-only and fail-closed by design.

## Core Capabilities

1. Include closure graph generation
- builds include dependency graph across `.c/.h`
- resolves include chains against source-tree paths
- classifies unresolved includes by severity (`critical`, `high`)

2. Symbol dependency reasoning
- maps symbol providers/consumers
- detects unresolved call sites
- verifies exported symbol provider availability
- records cross-driver dependency propagation

3. Kconfig cognition
- parses `config/menuconfig` dependency chains
- validates `depends on`, `select`, `imply` references
- detects impossible configuration chains and unknown refs

4. Makefile topology reasoning
- parses object inclusion lines
- maps object to source candidates and ordering
- detects missing object source closure

5. Compile boundary governance
- correlates patch-touched files with subsystem boundaries
- escalates when cross-subsystem changes touch runtime-sensitive regions

6. Runtime-aware compile strictness
- marks runtime-sensitive paths (`DSP/mailbox/IRQ/PCM/DAPM/SoundWire/PM`)
- increases fail-closed strictness for sensitive boundary crossings

7. Deterministic replay lineage
- persists compile cognition state and governance decisions
- supports replay reconstruction from persisted lineage only

## Execution Flow

1. ingest real source tree + patch context
2. build include closure graph
3. build symbol dependency graph
4. build Kconfig + Makefile compile topology maps
5. build compile boundary report from touched files
6. aggregate unresolved dependency report
7. compute compile confidence
8. apply fail-closed compile governance escalation
9. persist deterministic replay lineage

## Required Artifacts

- `include_closure_graph.json`
- `symbol_dependency_graph.json`
- `kconfig_dependency_map.json`
- `compile_boundary_report.json`
- `unresolved_dependency_report.json`
- `compile_governance_escalation.json`
- `deterministic_compile_replay.json`
- `compile_confidence_report.json`
- `subsystem_compile_topology.json`

## Governance Rules

Promotion is blocked (`FAIL_CLOSED`) when any of the following holds:

- include closure incomplete
- symbol lineage unresolved
- Kconfig dependency chain inconsistent
- subsystem compile topology not proven
- compile boundary crossing unsafe
- compile confidence below threshold

