# Component Registration (Blind v1)

## Core objects
- `snd_soc_component_driver`:
  - probe
  - controls
  - dapm widgets/routes
- `snd_soc_dai_driver`:
  - single playback DAI (`SPKR`)
- `snd_soc_dai_ops`:
  - `hw_params`, `hw_free`, `mute_stream`, `set_stream`

## Registration flow
- In SDW probe: initialize regmap, PM, then `devm_snd_soc_register_component`.
