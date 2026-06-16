# SoundWire Family

## Members
- qcom/sdw.c
- wcd*sdw
- wsa* (sdw)

## Family model
- Common architecture: controller + codec slave drivers.
- Common DAPM model: managed at codec/machine layers, transport exposes stream semantics.
- Common Runtime PM model: suspend/resume around regcache and stream state.
- Common DT model: SDW-compatible identifiers and endpoint properties.
- Common registration flow: sdw_driver + slave ops + ASoC component registration.
- Common patch structure: controller/codec split plus DT updates.
