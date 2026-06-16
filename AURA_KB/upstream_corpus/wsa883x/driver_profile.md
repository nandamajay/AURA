# Upstream Corpus Profile - wsa883x

## Architecture
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


## Patch history
# WSA883x Patch History

## Initial Upstreaming Series
- Series: `ASoC: codecs: add WSA883x support` (Patchwork series `654926`, v1, 2022-06-29).
- Patches included DT binding, codec core, controls/DAPM split.

## Merged Commits
- `16e2f8a4e9d5`: `ASoC: dt-bindings: Add WSA883x bindings`.
- `43b8c7dc85a1`: `ASoC: codecs: add wsa883x amplifier support`.
- `cdb09e623143`: `ASoC: codecs: wsa883x: add control, dapm widgets and map` (v3 accepted).
- `0df73e1a9f7b`: `ASoC: codecs: wsa883x: handle timeouts in resume path`.

## Version Evolution (Controls/DAPM patch)
- v1 (`12899625`): reviewed, superseded.
- v2 (`12900259`): reviewed, superseded.
- v3 (`12901777`): accepted by Mark Brown.

## Later Evolution Examples
- Port mapping support:
  - `49beb4d2e856` (DT), `1cf3295bd108` (driver).
- Shared reset GPIO support:
  - `126750523eac` (DT), `cf6518224776` (driver).


## Accepted commits
# WSA883x Accepted Commits

| Commit | Subject | Notes |
|---|---|---|
| `16e2f8a4e9d5` | ASoC: dt-bindings: Add WSA883x bindings | Initial binding |
| `43b8c7dc85a1` | ASoC: codecs: add wsa883x amplifier support | Initial codec core |
| `cdb09e623143` | ASoC: codecs: wsa883x: add control, dapm widgets and map | Accepted v3 |
| `0df73e1a9f7b` | ASoC: codecs: wsa883x: handle timeouts in resume path | Follow-up robustness fix |
| `1cf3295bd108` | ASoC: codecs: wsa883x: parse port-mapping information | Later feature evolution |
| `49beb4d2e856` | ASoC: dt-bindings: wsa883x: Document port mapping property | Matching DT schema evolution |
| `cf6518224776` | ASoC: codecs: wsa883x: Handle shared reset GPIO for WSA883x speakers | Shared reset support |
| `126750523eac` | ASoC: dt-bindings: qcom,wsa8830: Add reset-gpios for shared line | Matching binding update |


## Lore/review links
# WSA883x Lore/Patchwork Link Index

## Core Series (v1)
- Cover letter: https://lore.kernel.org/r/20220629090644.67982-1-srinivas.kandagatla@linaro.org
- [1/4] DT binding: https://lore.kernel.org/r/20220629090644.67982-2-srinivas.kandagatla@linaro.org
- [2/4] codec core: https://lore.kernel.org/r/20220629090644.67982-3-srinivas.kandagatla@linaro.org
- [3/4] controls/DAPM: https://lore.kernel.org/r/20220629090644.67982-4-srinivas.kandagatla@linaro.org

## Controls/DAPM revision chain
- v2: https://lore.kernel.org/r/20220629145831.77868-1-srinivas.kandagatla@linaro.org
- v3: https://lore.kernel.org/r/20220630123633.8047-1-srinivas.kandagatla@linaro.org

## Follow-up fix
- Resume timeout handling: https://lore.kernel.org/r/20220630130023.9308-2-srinivas.kandagatla@linaro.org

## Patchwork references
- Series v1: https://patchwork.kernel.org/project/alsa-devel/list/?series=654926
- Series v2: https://patchwork.kernel.org/project/alsa-devel/list/?series=655083
- Series v3: https://patchwork.kernel.org/project/alsa-devel/list/?series=655415


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
