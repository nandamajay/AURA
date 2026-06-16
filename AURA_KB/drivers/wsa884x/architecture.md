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
