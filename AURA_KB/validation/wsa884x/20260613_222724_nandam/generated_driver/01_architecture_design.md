# Architecture Design (Blind v1)

## Target architecture
- Upstream ASoC codec driver with native SoundWire slave integration.
- Ownership split:
  - Codec register/control/DAPM lifecycle in codec driver.
  - SoundWire stream lifecycle through SDW callbacks and DAI ops.

## Object model
- `struct wsa884x_priv`
  - regmap handle
  - sdw slave handle
  - runtime PM state
  - per-port enable/prepared state
  - DAPM/control runtime state (mode/speaker path params)

## Why this matches upstreaming rules
- Follows promoted ALSA rules (component/DAI primitives).
- Follows SoundWire rules (native SDW lifecycle usage).
- Follows patch-submission rules (clean split-ready architecture).
