# Phase 5 - Delta Report (v1)

## 1. DT schema mismatch (major)
- Generated approach:
  - `compatible` enum `qcom,wsa8840/qcom,wsa8845/...`
  - omitted strict supply requirements and exact `oneOf` constraint wording.
- Actual upstream approach:
  - `compatible: const: sdw20217020400`
  - requires `vdd-1p8-supply`, `vdd-io-supply`
  - explicit `oneOf` for `powerdown-gpios` vs `reset-gpios`.
- Why upstream won:
  - schema matched SoundWire enumeration model and strict dt-schema validation expectations.

## 2. Patch decomposition mismatch (major)
- Generated approach:
  - 7-patch staged series (DT/core/DAPM/controls/PM/SDW/docs).
- Actual upstream approach:
  - compact 2-patch initial series repeated v1->v4 (DT + codec), then targeted follow-ups.
- Why upstream won:
  - smaller ownership-focused series reduced coordination overhead and eased review iteration.

## 3. Reviewer-grounding mismatch (moderate)
- Generated approach:
  - explicit reviewer predictions for 5 maintainers.
- Actual evidence availability:
  - wsa884x direct comment transcripts sparse in current indexed corpus.
- Why upstream won:
  - reviewer-specific expectations must be tied to direct thread evidence per driver.

## 4. Runtime PM / SDW alignment (minor)
- Generated approach:
  - correct high-level PM and SDW lifecycle model.
- Actual upstream approach:
  - aligns closely with runtime hooks and SDW callbacks.
- Residual delta:
  - exact sequencing and helper usage details differ.
