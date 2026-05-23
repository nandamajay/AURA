# Governed Translation Intelligence Architecture

## Mission

Build an evidence-backed downstream-to-upstream translation intelligence layer
that remains governed, deterministic, and fail-closed.

This layer must not fabricate mappings and must not depend on heuristic-only
replacement suggestions.

## Inputs

- downstream driver/runtime/topology artifacts
- semantic equivalence artifacts
- runtime truth and portability artifacts
- structural extraction artifacts
- replay determinism traces
- governance state

## Translation Lifecycle

1. Plugin adapter ingestion (`runtime_conversion`, `topology_translation`,
   `downstream_upstream`, `structural_cognition`)
2. API replacement candidate synthesis (`api_replacement_map.json`)
3. Unsupported construct isolation (`unsupported_vendor_constructs.json`)
4. Lifecycle mapping graph generation (`lifecycle_translation_graph.json`)
5. Runtime equivalence validation (`runtime_equivalence_validation.json`)
6. AST-aware upstream plan generation (`upstream_translation_plan.json`)
7. Confidence + fail-closed gating (`translation_confidence_report.json`)
8. Deterministic replay lineage (`deterministic_translation_replay.json`)

## Evidence Backing Model

A mapping is accepted only when:

- upstream equivalent exists in mapping/equivalence artifacts
- semantic + structural/driver evidence supports the construct
- runtime compatibility checks do not reject it

Otherwise, the construct is moved to `unsupported_vendor_constructs.json` and
classification becomes fail-closed.

## AST-Aware Conversion Planning

`upstream_translation_plan.json` includes an `ast_aware_conversion_plan` with
stages tied to source-level extracted entities:

- ops structures
- proprietary hooks/callback chains
- routing structures
- DAI link structures

This keeps planning grounded in source artifacts rather than speculative rewrites.

## Governance Guarantees

- no autonomous patch generation
- no autonomous topology/runtime mutation
- fail-closed on unsupported or ambiguous constructs
- runtime-truth precedence over static assumptions
- advisory-only output behavior

## Replay Guarantees

Deterministic replay output includes:

- artifact fingerprint set
- replay signal lineage
- historical replay chain
- deterministic replay fingerprint

This ensures reproducible translation reasoning across sessions and restarts.

## Generated Outputs

- `upstream_translation_plan.json`
- `api_replacement_map.json`
- `unsupported_vendor_constructs.json`
- `lifecycle_translation_graph.json`
- `runtime_equivalence_validation.json`
- `translation_confidence_report.json`
- `deterministic_translation_replay.json`

## Operational Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-governed-translation-intelligence.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_translation_session_v1 \
  --lineage-id governed_translation_v1
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_governed_translation_intelligence_static.py \
  AURA/workspace/aura-sdk/tests/test_translation_intelligence_static.py -q
```
