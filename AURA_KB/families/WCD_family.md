# WCD Family

## Members
- wcd9335
- wcd934x
- wcd937x
- wcd938x
- wcd939x

## Family model
- Common architecture: codec core + accessory blocks (MBHC/irq/regmap), with separate SDW/SWR slave side when present.
- Common DAPM model: playback/capture widgets and full route tables.
- Common Runtime PM: present in upstreamed modern generations.
- Common DT model: per-generation qcom,wcd93xx schemas + sdw binding variants.
- Common registration flow: platform/bus probe then component/DAI registration.
- Common patch structure: multi-patch series (core, controls, DAPM/routes, bus side, bindings).
