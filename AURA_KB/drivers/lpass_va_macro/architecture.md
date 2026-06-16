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
