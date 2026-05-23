# Evidence Correlation

## Purpose
Correlate runtime, topology, semantic, replay, regression, capability, and governance domains into one evidence lineage model.

## Domains
- runtime evidence
- PCM activity
- mixer state
- topology cognition
- DTS cognition
- semantic cognition
- replay traces
- regression history
- plugin capability state
- governance decisions

## Outputs
- `evidence_lineage_graph.json`
- domain presence/completeness score
- mismatch classification
- evidence gap detection

## Determinism Rules
- correlation fingerprint derived from normalized domain payloads
- no target-specific branching in core correlation runtime
- adapter fingerprints included for plugin boundary verification
