# Upstream Corpus Profile - lpass_tx_macro

## Architecture
# lpass_tx_macro - architecture

## Driver inventory evidence
- Downstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/lpass-cdc/lpass-cdc-tx-macro.c` (`lpass_cdc_tx_macro_probe` ~2790; DAI ops ~1492; DAPM widgets ~1786).
- Upstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/lpass-tx-macro.c` (`tx_macro_component_probe` ~2109; DAI ops ~1213; DAPM widgets ~1420).
- Upstream DT binding: `qcom,lpass-tx-macro.yaml`.
- Upstream Kconfig: `config SND_SOC_LPASS_TX_MACRO` (~2916).
- Downstream build wiring: `audio-kernel-ar/asoc/codecs/lpass-cdc/Kbuild` has `CONFIG_LPASS_CDC_TX_MACRO` block (~110-112).

## Architecture comparison (evidence-backed)
- Platform macro codec architecture exists in both trees.
  - Lore evidence: accepted v5 core patches `12083061`, `12083063` (series `432165`).

## Reviewer mining status
- Patchwork comments endpoint for core patches returns empty arrays.
- Reviewer-comment transcript status: `INSUFFICIENT_EVIDENCE`.


## Patch history
# lpass_tx_macro - patch_history

- Core accepted series: `432165` (v5).
- Core lore links:
  - https://lore.kernel.org/r/20210211122735.5691-7-srinivas.kandagatla@linaro.org
  - https://lore.kernel.org/r/20210211122735.5691-8-srinivas.kandagatla@linaro.org

## Accepted core commits
- `12083061` -> `c39667ddcfc516fee084e449179d54430a558298`
- `12083063` -> `43cc3ef38de419f3f393b168f5f6c17f995f7473`


## Accepted commits
# lpass_tx_macro accepted commits (Patchwork commit_ref evidence)

- `12083061` -> `c39667ddcfc516fee084e449179d54430a558298`
- `12083063` -> `43cc3ef38de419f3f393b168f5f6c17f995f7473`


## Lore/review links
# lpass_tx_macro lore links

- https://lore.kernel.org/r/20210211122735.5691-7-srinivas.kandagatla@linaro.org
- https://lore.kernel.org/r/20210211122735.5691-8-srinivas.kandagatla@linaro.org
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
