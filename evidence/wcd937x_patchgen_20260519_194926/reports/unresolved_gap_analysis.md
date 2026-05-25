# Unresolved Gap Analysis

## Functional/Architecture Gaps
- Downstream-only abstractions unresolved: qti-regmap-debugfs, msm_cdc_* wrappers, wcdcal hwdep path.
- Proposed patches are mostly annotation/scoping deltas, not full behavioral upstream parity implementation.
- Governance decision for transformation proposal intentionally pending operator approval.

## Tooling/Environment Gaps
- Kernel tree not prepared for module compile (`include/generated/autoconf.h` and `include/config/auto.conf` missing).
- dt schema tool missing (`dt-doc-validate`).
- patchwise run did not complete within timeout window.

## Mapping Gaps (from authoritative mapping report)
- No confirmed direct upstream equivalent for qti-regmap-debugfs.
- No confirmed direct upstream equivalent for wcdcal hooks.
- No confirmed direct upstream equivalent for msm_cdc wrapper layer.
