# Upstream Corpus Profile - wsa884x

## Architecture
# wsa884x - architecture

## Driver inventory evidence
- Downstream driver: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa884x/wsa884x.c` (`wsa884x_codec_probe` ~1728, `soc_codec_dev_wsa884x_wsa` ~1821).
- Upstream driver: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wsa884x.c` (`wsa884x_codec_probe` ~1648, `wsa884x_component_drv` ~1760).
- Upstream DT binding: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wsa8840.yaml` (`compatible` around line 21).
- Downstream DT artifact: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-devicetree/wsa884x.dtsi`.
- Upstream Kconfig/Makefile: `Kconfig` has `config SND_SOC_WSA884X` (~2765), `Makefile` has `snd-soc-wsa884x-y := wsa884x.o` (~428).
- Downstream build wiring: `audio-kernel-ar/asoc/codecs/wsa884x/Kbuild` has `CONFIG_SND_SOC_WSA884X` object block (~66-70).

## Architecture comparison (evidence-backed)
- Probe/registration exists on both sides (downstream component probe + upstream SDW probe/register).
  - Lore evidence: accepted core patch `13282701` (series `757854`) commit `aa21a7d4f68a0a5067578cbb93c136ab5ac09cfa`.
- DAPM + controls exist on both sides (`wsa884x_dapm_widgets`, `wsa884x_snd_controls` families).
  - Lore evidence: v1->v4 progression (`755223` -> `756050` -> `756224` -> `757854`).
- Runtime PM + SoundWire integration exists on both sides.
  - Lore evidence: paired DT+codec patches accepted (`13282700`, `13282701`).

## Reviewer mining status
- Patchwork comments endpoints for core revisions return empty arrays.
- Reviewer-comment transcript status: `INSUFFICIENT_EVIDENCE`.


## Patch history
# wsa884x - patch_history

## Lore/Patchwork timeline
- v1: series `755223` (`13271787`, `13271786`) - superseded.
- v2: series `756050` (`13275178`, `13275179`) - superseded.
- v3: series `756224` (`13276223`, `13276224`) - superseded.
- v4: series `757854` (`13282700`, `13282701`) - accepted.

## Accepted core commits (Patchwork commit_ref)
- `13282700` -> `fd012bc60dc63d239f8d27e230f6768e74613f5e`
- `13282701` -> `aa21a7d4f68a0a5067578cbb93c136ab5ac09cfa`


## Accepted commits
# wsa884x accepted commits (Patchwork commit_ref evidence)

- `13282700` -> `fd012bc60dc63d239f8d27e230f6768e74613f5e`
- `13282701` -> `aa21a7d4f68a0a5067578cbb93c136ab5ac09cfa`
- `13487056` -> `6fd566129ceef1852ec8f999ec9de6f3187f32ff`
- `13565442` -> `8f7ce92abf1300f671ca37f0f7c4f1f4d95a31d4`
- `13714486` -> `e96f7f3f6770748f1fd65ebec82c3534d2ac66f7`


## Lore/review links
# wsa884x lore links

- https://lore.kernel.org/r/20230608085023.141745-1-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230608085023.141745-2-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230611102657.74714-1-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230611102657.74714-2-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230612095716.118631-1-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230612095716.118631-2-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230616115751.392886-1-krzysztof.kozlowski@linaro.org
- https://lore.kernel.org/r/20230616115751.392886-2-krzysztof.kozlowski@linaro.org


## Maintainers involved
- Mark Brown
- Pierre-Louis Bossart
- Krzysztof Kozlowski
- Vinod Koul (where transport touched)
- Bjorn Andersson (where arm-msm path touched)

## Subsystems touched
- ASoC
- Codec
- DAPM
- Runtime PM
- DT bindings
- SoundWire (where applicable)
