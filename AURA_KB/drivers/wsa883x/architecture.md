# WSA883x Architecture (Downstream vs Final Upstream)

## Evidence
- Downstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa883x/wsa883x.c`
- Upstream: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c`
- Upstream DT schema: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wsa883x.yaml`

## Final Upstream Component Model
- `snd_soc_component_driver`: controls, DAPM widgets/routes, probe registration.
- Evidence: upstream `wsa883x.c:1327-1336`.

## Final Upstream DAI Model
- `snd_soc_dai_ops`: `hw_params`, `hw_free`, `mute_stream`, `set_stream`.
- `snd_soc_dai_driver`: single playback DAI (`SPKR`).
- Evidence: upstream `wsa883x.c:1404-1425`.

## Final Upstream SoundWire Model
- Uses generic SDW framework: `sdw_slave_ops`, `sdw_stream_add_slave`, `sdw_stream_remove_slave`, `sdw_driver`.
- Evidence: upstream `wsa883x.c:1126-1129`, `1356-1367`, `1717-1728`.

## Final Upstream Runtime PM
- Runtime PM autosuspend + runtime suspend/resume handlers.
- Evidence: upstream `wsa883x.c:1668-1672`, `1686-1708`.

## Final Upstream DAPM and Controls
- DAPM: `IN -> SPKR`.
- Controls include PA volume, mode, comp offset, and SWR port switches.
- Evidence: upstream `wsa883x.c:1301-1325`.

## Downstream Architectural Differences
- Uses Qualcomm SWR framework (`swr_driver`, `swr_connect_port`, `swr_disconnect_port`) rather than generic SDW APIs.
- Exposes machine-driver coupling helpers (`wsa883x_set_channel_map`, `wsa883x_codec_get_dev_num`) consumed by downstream machine drivers.
- Evidence: downstream `wsa883x.c:2208-2231`, `1102-1135`; `wsa883x.h:15-23`; `audio_machine.c:2185-2390`.

## Why Upstream Chose This Design
- Align with ALSA ASoC + SoundWire subsystem contracts.
- Reduce vendor-specific coupling and keep codec logic framework-native.
- Review-driven tightening of PM/error and control semantics (see `patch_history.md` and `review_comments.md`).
