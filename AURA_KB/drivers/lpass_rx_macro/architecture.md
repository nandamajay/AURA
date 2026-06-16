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
