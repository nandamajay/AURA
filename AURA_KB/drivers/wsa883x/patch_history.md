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
