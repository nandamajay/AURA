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
