# Real Source-Tree Governed Conversion Architecture

## Objective

Ingest real Qualcomm downstream audio source trees and produce governed,
deterministic, replay-safe downstream-to-upstream conversion cognition.

## Scope

Allowed:

- tiny wrapper/helper normalization
- debug/log abstraction cleanup
- trivial API substitutions with explicit evidence
- capability wrapper normalization classification

Blocked:

- large topology rewrites
- DSP architecture redesign
- FE/BE redesign
- SoundWire architecture migration
- unsafe semantic rewrites

## Ingestion Coverage

- `.c`
- `.h`
- `Kconfig`
- `Makefile`

## Cognition Outputs

- source tree file graph and include dependency graph
- subsystem boundary segmentation
- symbol definition/use dependency graph
- wrapper classification and upstream equivalence mapping
- governed conversion plan (approved/blocked transformations)
- compile-oriented validation report
- runtime-sensitive region inventory
- governance escalation report
- deterministic replay lineage
- real patch proposal

## Governance

Fail-closed escalation triggers include:

- runtime-sensitive regions affected
- compile integrity uncertain or failed
- symbol lineage inconsistency
- include/dependency graph inconsistency
- runtime confidence below threshold
- no safe transformations available

## Determinism

Every artifact is fingerprinted and replayed through lineage-indexed history.
Patch text and changed file list are included in deterministic replay payloads.
