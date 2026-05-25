# Semantic Runtime Validation Report

## Mode
- semantic/runtime analysis mode: `enabled`
- compile closure influence on semantic confidence: `none`
- governance posture: `fail_closed_on_semantic_ambiguity`

## Inputs
- compile continuation run: `/local/mnt/workspace/AURA_V1/evidence/compile_closure_wcd937x_continuation_20260520_033221`
- downstream/upstream mapping evidence: `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/artifacts/downstream_upstream_mapping.json`
- symbol probes: downstream/upstream JSON artifacts
- patch proposals: `/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926/generated_patch_diffs`

## PHASE A — Structural Runtime Mapping
- SoundWire mapping exists structurally (`swr_` downstream vs `sdw_` upstream), but is inferred.
- MBHC symbols exist on both sides, but callback semantics are not proven.
- Probe/remove and DAI/stream hooks are present upstream and referenced downstream.
- Missing runtime hooks/effects remain unresolved due absent runtime traces.

## PHASE B — Behavioral Semantic Analysis
- MBHC behavior parity: `UNKNOWN`
- Regulator sequencing parity: `UNKNOWN`
- Calibration ownership parity: `NOT_ESTABLISHED` (upstream equivalent unresolved)
- Hidden downstream assumptions likely in wrapper layers (`msm_cdc_*`, `qti-regmap-debugfs`, `wcd_irq_*`, `wcdcal_*`).

## PHASE C — ALSA Surface Comparison
- Upstream controls/widgets/routes detected from source.
- Downstream ALSA surface evidence is partial-only.
- ALSA parity classification: `UNKNOWN`.

## PHASE D — Runtime Risk Classification
- compile-safe but runtime-unsafe/unknown zones identified (see `runtime_risk_classification.md`).
- high-risk semantic zones remain unresolved and escalated.

## PHASE E — Governance Scoring
- semantic_confidence_score: `0.23`
- runtime_equivalence_score: `0.17`
- upstream_behavioral_readiness: `advisory_only`
- unresolved_runtime_risks: `9`

## Compile Closure Constraint
- Compile closure was achieved (`CLOSED`), but semantic/runtime confidence was not elevated from compile success.

## Mandatory Classification
- advisory_only
- runtime_unverified
- escalation_required

## Explicit Non-Claims
- no SoundWire runtime parity claim
- no MBHC parity claim
- no regulator timing parity claim
- no calibration ownership parity claim
- no DAPM/ALSA behavioral parity claim
- no merge readiness claim

## Patchset Semantic Context
- Patch proposals are primarily annotation/governance oriented.
- Patch profile summary: `[{'patch': '0001-ASoC-codecs-wcd937x-annotate-build-wiring-constraint.patch', 'added_lines': 5, 'removed_lines': 2, 'effective_code_like_additions': 1}, {'patch': '0002-ASoC-codecs-wcd937x-add-core-port-migration-guardrai.patch', 'added_lines': 7, 'removed_lines': 1, 'effective_code_like_additions': 0}, {'patch': '0003-ASoC-codecs-wcd937x-sdw-document-SWR-to-SDW-migratio.patch', 'added_lines': 5, 'removed_lines': 1, 'effective_code_like_additions': 0}, {'patch': '0004-ASoC-codecs-add-MBHC-CLSH-conversion-alignment-notes.patch', 'added_lines': 10, 'removed_lines': 1, 'effective_code_like_additions': 0}, {'patch': '0005-ASoC-codecs-wcd937x-record-downstream-abstraction-ex.patch', 'added_lines': 8, 'removed_lines': 1, 'effective_code_like_additions': 0}, {'patch': '0006-dt-bindings-sound-qcom-wcd937x-clarify-upstream-sche.patch', 'added_lines': 2, 'removed_lines': 1, 'effective_code_like_additions': 2}]`
- This profile does not constitute runtime behavioral proof.

## Evidence References
- `/local/mnt/workspace/AURA_V1/evidence/compile_closure_wcd937x_continuation_20260520_033221/reports/compile_closure_status.md`
- `/local/mnt/workspace/AURA_V1/evidence/compile_closure_wcd937x_continuation_20260520_033221/reports/human_escalation_review.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/downstream_upstream_api_mapping_report.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/dependency_graph_report.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/semantic_transformation_plan.md`
