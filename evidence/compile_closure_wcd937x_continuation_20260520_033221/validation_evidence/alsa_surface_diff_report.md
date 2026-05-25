# ALSA Surface Diff Report

## Scope and Limits
- This pass compares ALSA/DAPM indicators using available evidence only.
- Full downstream control/widget/route inventory is **not** present in local artifacts.
- Therefore ALSA parity remains `UNKNOWN`.

## Upstream Surface Indicators (from `sound/soc/codecs/wcd937x.c`)
- `SOC_SINGLE*`/`SOC_ENUM*` control definitions: present
- `wcd937x_snd_controls[]`: present
- `wcd937x_dapm_widgets[]` and `wcd937x_audio_map[]`: present
- Representative outputs: `EAR`, `AUX`, `HPHL`, `HPHR`, `ADC*_OUTPUT`

## Downstream Surface Indicators (from symbol probes, partial)
- `SND_SOC_DAPM_` mentions in captured probe rows: `8`
- `SND_JACK` mentions in captured probe rows: `4`
- Full control table dump: `missing`
- Full widget graph dump: `missing`
- Full route graph dump: `missing`

## Diff Classification
- Control-name parity: `UNKNOWN`
- Widget parity: `UNKNOWN`
- Route parity: `UNKNOWN`
- Runtime ALSA behavior parity: `UNKNOWN`

## Classification
- advisory_only
- runtime_unverified
- escalation_required
