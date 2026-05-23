# Replay Lineage

## Purpose
Define deterministic replay lineage behavior for unified multi-domain cognition correlation.

## Lineage Guarantees
- Correlation lineage is persisted in `aura_cognition_registry.json` under `cognition_correlation.history`.
- Replay reconstruction uses lineage ID + correlation fingerprint + artifact paths.
- Replay payload emits deterministic replay fingerprint independent of process restarts.

## Required Inputs
- runtime evidence lineage
- topology cognition lineage
- semantic cognition lineage
- regression lineage
- governance state snapshot

## Replay Output
- `cognition_fusion_trace.json` contains replay fingerprint, lineage ID, and artifact references.
- Replay is fail-closed when lineage is missing or invalid.
