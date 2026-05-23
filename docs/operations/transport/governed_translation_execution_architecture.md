# Governed Translation Execution Architecture

## Mission

Execute evidence-backed downstream-to-upstream transformations with strict
fail-closed governance and deterministic replay lineage.

This layer consumes translation intelligence outputs but never mutates runtime
state and never performs autonomous source patching.

## Inputs

- `upstream_translation_plan.json`
- `api_replacement_map.json`
- `unsupported_vendor_constructs.json`
- `runtime_equivalence_validation.json`
- `translation_confidence_report.json`
- `runtime_truth_graph.json` (runtime-truth precedence gate)
- cognition governance state + replay determinism trace
- source snapshots (`--source-manifest` and/or `--source-file`)

## Execution Lifecycle

1. Load translation/runtime/governance artifacts.
2. Evaluate fail-closed governance posture.
3. Reject execution when unsupported constructs or low confidence remain.
4. Build runtime-validated transformation candidates.
5. Apply AST-aware identifier replacement (comment/string-safe).
6. Construct rollback-safe patch chunks and lineage.
7. Generate deterministic fingerprints and replay payload.
8. Persist artifacts + cognition lineage.

## Governed Capabilities

- callback replacement transformation
- vendor macro elimination
- FE/BE topology rewrite scaffolding
- DAPM route conversion generation
- SoundWire upstream adaptation
- runtime-safe API substitution
- migration staging boundaries
- rollback-safe patch chunking

## Fail-Closed Rules

Execution is blocked when any condition is true:

- governance posture is violated
- unsupported vendor constructs remain unresolved
- runtime equivalence report is fail-closed
- translation confidence is below threshold
- no runtime-validated transform candidates remain
- no transformations are applied

Blocked mode produces a guarded patch header (`mode=blocked`) and zero applied
segments.

## Determinism + Replay

Deterministic artifacts:

- `generated_upstream_patch.diff`
- `transformation_lineage.json`
- `unsafe_transformation_blocks.json`
- `runtime_validated_patch_segments.json`
- `deterministic_patch_generation_replay.json`
- `translation_execution_report.json`

Replay includes deterministic fingerprint lineage and persisted artifact paths.

## Operational Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-governed-translation-execution.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_translation_execution_session_v1 \
  --lineage-id governed_translation_execution_v1 \
  --dry-run
```

Optional source input:

```bash
--source-root /path/to/downstream/tree \
--source-file sound/soc/qcom/qdsp6/q6apm-dai.c \
--source-file sound/soc/qcom/qdsp6/q6apm-lpass-dais.c
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_governed_translation_execution_static.py \
  AURA/workspace/aura-sdk/tests/test_governed_translation_intelligence_static.py -q
```

## Architectural Boundaries

- advisory-only behavior
- no autonomous patch submission
- no runtime mutation
- runtime truth precedence
- plugin-isolated target logic (no core `if target == ...` branching)
