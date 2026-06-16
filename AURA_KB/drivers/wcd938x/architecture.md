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
