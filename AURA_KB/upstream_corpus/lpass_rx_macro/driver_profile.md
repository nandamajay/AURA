# Upstream Corpus Profile - lpass_rx_macro

## Architecture
# lpass_rx_macro - architecture

## Driver inventory evidence
- Downstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/lpass-cdc/lpass-cdc-rx-macro.c` (`lpass_cdc_rx_macro_probe` ~4829; DAI ops ~746; DAPM widgets ~3984).
- Upstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/lpass-rx-macro.c` (`rx_macro_component_probe` ~3606; DAI ops ~1954; DAPM widgets ~3133).
- Upstream DT binding: `qcom,lpass-rx-macro.yaml`.
- Upstream Kconfig: `config SND_SOC_LPASS_RX_MACRO` (~2910).
- Downstream build wiring: `audio-kernel-ar/asoc/codecs/lpass-cdc/Kbuild` has `CONFIG_LPASS_CDC_RX_MACRO` block (~114-116).

## Architecture comparison (evidence-backed)
- Both implement platform macro codec with component/DAI/DAPM/control layers.
  - Lore evidence: accepted v5 core patches `12083053`, `12083055` in series `432165`.

## Reviewer mining status
- Patchwork comments endpoint for core patches returns empty arrays.
- Reviewer-comment transcript status: `INSUFFICIENT_EVIDENCE`.


## Patch history
# lpass_rx_macro - patch_history

- Core accepted series: `432165` (v5).
- Core lore links:
  - https://lore.kernel.org/r/20210211122735.5691-3-srinivas.kandagatla@linaro.org
  - https://lore.kernel.org/r/20210211122735.5691-4-srinivas.kandagatla@linaro.org

## Accepted core commits
- `12083053` -> `af3d54b99764f0bdd83fcbd1895d23b83f8276be`
- `12083055` -> `c1ba6bd0d1f2f1dd6b6f1f78a2b2c744adad3eaf`


## Accepted commits
# lpass_rx_macro accepted commits (Patchwork commit_ref evidence)

- `12083053` -> `af3d54b99764f0bdd83fcbd1895d23b83f8276be`
- `12083055` -> `c1ba6bd0d1f2f1dd6b6f1f78a2b2c744adad3eaf`


## Lore/review links
# lpass_rx_macro lore links

- https://lore.kernel.org/r/20210211122735.5691-3-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210211122735.5691-4-srinivas.kandagatla@linaro.org
- https://patchwork.kernel.org/project/alsa-devel/list/?series=432165


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
