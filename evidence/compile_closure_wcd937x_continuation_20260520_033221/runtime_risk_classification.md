# Runtime Risk Classification

## Compile-Safe but Runtime-Unsafe/Unknown Zones
- SoundWire topology and interrupt semantics
- MBHC callback and jack-detection behavior
- Regulator sequencing/timing behavior
- Calibration ownership transition (`wcdcal` unresolved)
- Downstream wrapper removal side effects (`msm_cdc_*`, `qti-regmap-debugfs`, `wcd_irq_*`)
- DT ABI runtime behavior impacts

## Semantic Uncertainty Zones
- DAPM route behavior parity
- ALSA control exposure parity
- Runtime PM ordering parity
- Probe/remove side-effect parity

## Classification Outcome
- semantic_confidence_score: `0.23`
- runtime_equivalence_score: `0.17`
- upstream_behavioral_readiness: `advisory_only`
- mandatory classification: `advisory_only`, `runtime_unverified`, `escalation_required`

## Governance Guard
- Merge-readiness classification is prohibited in this semantic mode.
