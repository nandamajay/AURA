# Upstream Corpus Profile - wcd938x

## Architecture
# wcd938x - architecture

## Driver inventory evidence
- Downstream core: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x.c` (`soc_codec_dev_wcd938x` ~4153, `wcd938x_dai[]` ~4356).
- Downstream SoundWire-side file: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x-slave.c` (`wcd938x_swr_probe` ~336).
- Upstream core: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c` (`soc_codec_dev_wcd938x` ~3165).
- Upstream SDW: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c` (`wcd9380_probe` ~1152).
- Upstream DT bindings: `qcom,wcd938x.yaml`, `qcom,wcd938x-sdw.yaml`.
- Upstream Kconfig entries: `SND_SOC_WCD938X` / `SND_SOC_WCD938X_SDW`.
- Downstream build wiring: `audio-kernel-ar/asoc/codecs/wcd938x/Kbuild` has `CONFIG_SND_SOC_WCD938X` object block (~75-80).

## Architecture comparison (evidence-backed)
- Both trees implement codec-core + SoundWire-side split.
  - Lore evidence: accepted core v9 patches `12309349` (codec) and `12309351` (SDW).
- Both carry controls/DAPM/routes at codec layer.
  - Lore evidence: accepted patches `12309355`, `12309357`, `12309359`, `12309361`.

## Reviewer mining status
- Patchwork comments endpoint returns empty arrays for sampled core patches.
- Reviewer-comment transcript status: `INSUFFICIENT_EVIDENCE`.


## Patch history
# wcd938x - patch_history

## Lore/Patchwork timeline (captured evidence)
- v1 cover observed: `20210311173416.25219-1`.
- v2 cover observed: `20210316105828.16436-1`.
- v3 cover observed: `20210319092919.21218-1`.
- Final accepted core set observed as v9 series `496971`.

## Accepted core commits (Patchwork commit_ref)
- `12309349` -> `8d78602aa87a3805902bed83157526fdc5b837d4`
- `12309351` -> `f1e3a0af90bcf6b4aa89fc67fbe5f648ef44a860`
- `12309355` -> `a5e823e9426f1af6d00ff07f7f4d9f75bd72ecea`
- `12309357` -> `84de91f3f10047c5f5476abdd9f5f183aa5d1c48`
- `12309359` -> `9886f3ec97c64033fb73358be6f5531c97f94d8e`
- `12309361` -> `2f9ef38f0f38cbe5db1fd91dcebb9837ebe5f50f`


## Accepted commits
# wcd938x accepted commits (Patchwork commit_ref evidence)

- `12309349` -> `8d78602aa87a3805902bed83157526fdc5b837d4`
- `12309351` -> `f1e3a0af90bcf6b4aa89fc67fbe5f648ef44a860`
- `12309355` -> `a5e823e9426f1af6d00ff07f7f4d9f75bd72ecea`
- `12309357` -> `84de91f3f10047c5f5476abdd9f5f183aa5d1c48`
- `12309359` -> `9886f3ec97c64033fb73358be6f5531c97f94d8e`
- `12309361` -> `2f9ef38f0f38cbe5db1fd91dcebb9837ebe5f50f`


## Lore/review links
# wcd938x lore links

- https://lore.kernel.org/r/20210311173416.25219-1-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210316105828.16436-1-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210319092919.21218-1-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210609090943.7896-4-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210609090943.7896-6-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210609090943.7896-10-srinivas.kandagatla@linaro.org


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
