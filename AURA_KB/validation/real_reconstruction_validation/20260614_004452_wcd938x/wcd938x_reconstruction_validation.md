# WCD938X Reconstruction Validation

## Inputs and constraints
Used:
- Downstream implementation: `audio-kernel-ar/asoc/codecs/wcd938x/*`
- Existing AURA KB rules, patterns, maintainer models, playbooks
- Existing lore/accepted-commit artifacts for `wcd938x`

Not used for generation phase:
- Upstream implementation files (`linux-next/.../wcd938x*.c`, binding yaml)

## 1. Downstream understanding model
Observed downstream architecture:
- Primary codec platform driver with large codec responsibilities and vendor-specific PM hooks.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x.c:4153-4165`, `:4753-4773`
- Separate vendor SoundWire slave module (`wcd938x-slave.c`) using `swr_driver` and component bind/unbind.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x-slave.c:331-408`
- DAPM and controls are extensive (large table-driven graph and controls).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x.c:3092-3126`, `:3362`, `:4157-4162`
- SoundWire enumeration and binding are vendor-orchestrated with `component_bind_all` and SWR device matching.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x.c:4380-4410`

## 2. Blind upstream reconstruction (downstream + KB only)
Predicted upstream solution:
1. Keep split ownership between core codec driver and SoundWire transport side.
2. Use framework-native registration (`snd_soc_component_driver` + static `snd_soc_dai_driver`).
3. Keep large control/DAPM graph, but remove vendor-only glue where possible.
4. Move SoundWire transport callbacks to SDW-native API path.
5. Use runtime PM for SDW transport and avoid vendor-only suspend semantics where possible.
6. Preserve DT split between core codec binding and SDW endpoint binding.

Reasoning sources:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/validated_learning_extraction.md`

## 3. Reconstructed patch-series (predicted)
Predicted shape:
- PATCH 1: dt-bindings: add/adjust `qcom,wcd938x.yaml`
- PATCH 2: dt-bindings: add/adjust `qcom,wcd938x-sdw.yaml`
- PATCH 3: codecs: wcd938x core codec/platform driver
- PATCH 4: codecs: wcd938x SDW transport side (`wcd938x-sdw.c`)
- PATCH 5: codecs: controls/DAPM/routing enablement
- PATCH 6: follow-up PM/robustness fixes (if review requests)

## 4. Reviewer simulation (pre-reveal)
- Mark Brown: kcontrol semantics, patch partitioning, ASoC model correctness.
- Pierre-Louis Bossart: SDW lifecycle correctness, PM interactions.
- Krzysztof Kozlowski: DT schema split and property validity.
- Vinod Koul/Bjorn Andersson: SoundWire and Qualcomm integration concerns.

Comment confidence:
- Mark/Pierre: MEDIUM
- Krzysztof: LOW-MEDIUM
- Vinod/Bjorn: LOW

## 5. Upstream reveal (answer key)
Ground truth in upstream:
- Core codec remains platform driver (`wcd938x.c`).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3546-3556`
- SoundWire side exists as separate `sdw_driver` module (`wcd938x-sdw.c`).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1146-1150`, `:1264-1274`
- Core DAI ops route to SDW helper path (`hw_params`, `hw_free`, `set_stream`).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3273-3306`
- Runtime PM is explicit on SDW side (`RUNTIME_PM_OPS`).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1233-1261`
- DT remains split across codec and SDW endpoint schemas.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wcd938x.yaml:20-39`, `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wcd938x-sdw.yaml:17-44`

## 6. Summary
Generalization from WSA883x worked for:
- framework-native registration direction
- SDW-native transport ownership
- DT split expectations

Generalization gaps remain around:
- family-specific WCD complexity (MBHC/jack/micbias and larger DAPM/control surface)
- reviewer prediction due to sparse direct review text in `wcd938x` corpus artifacts

