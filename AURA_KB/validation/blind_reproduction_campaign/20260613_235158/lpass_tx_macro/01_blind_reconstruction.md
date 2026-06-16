# Blind Reconstruction - lpass_tx_macro

Generation constraint: downstream source + AURA_KB rules/patterns/playbooks only.

- Downstream source: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/lpass-cdc/lpass-cdc-tx-macro.c`
- Reconstructed upstream-intent design:
  - framework-native ASoC component/DAI registration
  - LPASS macro platform-driver style with DAPM/route centric structure
  - runtime PM integration and robust error-path handling
