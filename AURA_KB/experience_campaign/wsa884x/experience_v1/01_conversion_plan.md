# Phase 1 - Real Conversion Planning (WSA884x)

## Scope and constraints
- Campaign type: experience-generation only.
- Inputs used: existing AURA_KB rules, patterns, maintainer models, playbooks, prior WSA884x validation outputs.
- No new mining, no reviewer-corpus expansion, no benchmark-method change.

## 1. Upstream architecture plan
- Use a framework-native ASoC codec driver with SoundWire integration and runtime PM.
- Keep ownership clean: codec/component responsibilities in codec driver; no board policy embedded.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/alsa_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/architecture.md`

## 2. Expected file layout
- `Documentation/devicetree/bindings/sound/qcom,wsa8840.yaml`
- `sound/soc/codecs/wsa884x.c`
- Update `sound/soc/codecs/Kconfig`
- Update `sound/soc/codecs/Makefile`
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/architecture.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`

## 3. DT strategy
- DT binding first, schema-strict, minimal required properties, compatible expansion controlled.
- Pair DT patch with core driver enablement in same series.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/dt_binding_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_dt_binding.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/patch_history.md`

## 4. SoundWire strategy
- SDW lifecycle via generic APIs; explicit stream lifecycle and callback-state guards.
- Keep SoundWire ownership boundaries clean; avoid controller/machine leakage into codec.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_soundwire_driver.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/pierre_bossart_acceptance_model.md`

## 5. DAPM strategy
- Start with explicit but minimal widget/route set required for functional path.
- Avoid oversized graph in initial submission; expand later only if needed.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/dapm_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`

## 6. Runtime PM strategy
- Include runtime PM in initial core driver series.
- Resume path must be timeout-safe before cache-sensitive operations.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/pierre_bossart_acceptance_model.md`

## 7. Control registration strategy
- Keep control set reviewable; enforce ALSA put semantics.
- Prefer clear naming and constrained feature surface in v1.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/alsa_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/mark_brown.md`

## 8. Component registration strategy
- Register standard `snd_soc_component_driver` + `snd_soc_dai_driver` objects.
- Use managed registration and standard callback tables.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/alsa_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`

## 9. Patch decomposition strategy
- v1 plan (intentional first pass) will be decomposed by ownership but slightly over-split to simulate real review pressure.
- v2 plan will be tightened based on simulated review outcomes.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/wsa884x/20260613_222724_nandam/scorecards/phase5_similarity_v1.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/wsa884x/20260613_222724_nandam/iteration_v2/scorecards/phase7_v2_similarity.md`
