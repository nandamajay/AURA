# Upstream Corpus Profile - lpass_va_macro

## Architecture
# lpass_va_macro - architecture

## Driver inventory evidence
- Downstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/lpass-cdc/lpass-cdc-va-macro.c` (`lpass_cdc_va_macro_probe` ~2487; DAI ops ~1564; DAPM widgets ~1747).
- Upstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/lpass-va-macro.c` (`va_macro_component_probe` ~1325; DAI ops ~946; DAPM widgets ~1109).
- Upstream DT binding: `qcom,lpass-va-macro.yaml`.
- Upstream Kconfig: `config SND_SOC_LPASS_VA_MACRO` (~2904).
- Downstream build wiring: `audio-kernel-ar/asoc/codecs/lpass-cdc/Kbuild` has `CONFIG_LPASS_CDC_VA_MACRO` block (~106-108).

## Architecture comparison (evidence-backed)
- Platform macro codec architecture exists in both trees.
  - Lore evidence: accepted v3 core patches `11883973`, `11883979` (series `378089`).

## Reviewer mining status
- Patchwork comments endpoint for core patches returns empty arrays.
- Reviewer-comment transcript status: `INSUFFICIENT_EVIDENCE`.


## Patch history
# lpass_va_macro - patch_history

- Core accepted series: `378089` (v3).
- Core lore links:
  - https://lore.kernel.org/r/20201105113458.12360-6-srinivas.kandagatla@linaro.org
  - https://lore.kernel.org/r/20201105113458.12360-7-srinivas.kandagatla@linaro.org

## Accepted core commits
- `11883973` -> `908e6b1df26efc9d2df70c9a7bf4f5eae5c5702f`
- `11883979` -> `e8c6f128f7c2f9ee72ec14fa6200a2ca4f79a5cc`


## Accepted commits
# lpass_va_macro accepted commits (Patchwork commit_ref evidence)

- `11883973` -> `908e6b1df26efc9d2df70c9a7bf4f5eae5c5702f`
- `11883979` -> `e8c6f128f7c2f9ee72ec14fa6200a2ca4f79a5cc`


## Lore/review links
# lpass_va_macro lore links

- https://lore.kernel.org/r/20201105113458.12360-6-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20201105113458.12360-7-srinivas.kandagatla@linaro.org
- https://patchwork.kernel.org/project/alsa-devel/list/?series=378089


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
