# Phase 1 - Ground Truth Evidence Index (References Only)

## Downstream implementation
- Driver core: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa884x/wsa884x.c`
  - probe/remove path (SWR): `wsa884x_swr_probe` (~2118), `wsa884x_swr_remove` (~2533)
  - ASoC component registration objects around lines ~1821, ~2027
  - DAPM/widgets/controls around lines ~1281, ~1535
- Build glue: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa884x/Kbuild`
- Downstream DT artifact: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-devicetree/wsa884x.dtsi`

## Upstream implementation (answer key for later scoring)
- Upstream driver: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wsa884x.c`
- Upstream DT schema: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wsa8840.yaml`
- Upstream Kconfig/Makefile references:
  - `.../linux-next/sound/soc/codecs/Kconfig` (`config SND_SOC_WSA884X`)
  - `.../linux-next/sound/soc/codecs/Makefile` (`snd-soc-wsa884x-y := wsa884x.o`)

## Lore / patch history
- Stored index: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wsa884x.md`
- Key revisions captured: v1 -> v2 -> v3 -> v4 accepted.

## Accepted commits
- Stored index: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/accepted_commits/wsa884x.md`
- Includes core accepted patch commit refs and follow-up accepted commits.

## Review discussions
- `wsa884x` direct comment transcript quality: `INSUFFICIENT_EVIDENCE` (patchwork comments not fully indexed in KB).
- Maintainer expectation proxies used for simulation:
  - `review_database/mark_brown/*/wsa883x.md`
  - `review_database/pierre_bossart/*/wsa883x.md`
  - Maintainer models under `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/`

## Generation guardrail
- Upstream implementation is treated as answer key and not copied.
- Blind generation uses downstream + KB rules/patterns/playbooks.
