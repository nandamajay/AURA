# Governed Adaptive Remediation and Translation Learning Architecture

## Mission

Learn from governed translation outcomes and manual remediation decisions while
preserving fail-closed governance and runtime-truth precedence.

The layer is advisory and deterministic. It never bypasses governance gates and
never enables autonomous patching.

## Inputs

- `api_replacement_map.json`
- `runtime_equivalence_validation.json`
- `runtime_validated_patch_segments.json`
- `translation_execution_report.json`
- `transformation_lineage.json`
- `unsafe_transformation_blocks.json`
- `unsupported_vendor_constructs.json`
- optional `manual_remediation_outcomes.json`
- governance state + replay determinism signal

## Learning Lifecycle

1. Validate governance posture (fail-closed flags must remain enforced).
2. Correlate candidate mappings with runtime-validated patch segments.
3. Merge manual remediation outcomes into translation pattern memory.
4. Calibrate confidence using historical and runtime-backed evidence.
5. Detect recurring blocker similarity signatures.
6. Extract reusable remediation templates by category/subsystem.
7. Build reusable equivalence library and subsystem translation memory.
8. Persist deterministic lineage trace.

## Required Outputs

- `learned_translation_patterns.json`
- `remediation_template_registry.json`
- `historical_blocker_similarity_map.json`
- `confidence_calibration_report.json`
- `reusable_equivalence_library.json`
- `subsystem_translation_memory.json`
- `adaptive_remediation_trace.json`

## Governance Enforcement

- no learned pattern may bypass fail-closed behavior without runtime-backed evidence
- no autonomous runtime/source mutation
- no autonomous patch submission
- runtime-truth precedence over static assumptions

If runtime-backed evidence is insufficient, classification remains fail-closed
and patterns remain non-reusable for governed execution.

## Determinism

All outputs include deterministic fingerprints and sorted ordering. Replay state
is persisted in the cognition registry and can be reconstructed across sessions.

## Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-governed-adaptive-remediation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_adaptive_remediation_session_v1 \
  --lineage-id governed_adaptive_remediation_v1
```

Optional manual learning input:

```bash
--manual-remediation-file /path/to/manual_remediation_outcomes.json
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_governed_adaptive_remediation_static.py -q
```
