# RB3 Runtime Validation Correlation

## Correlated evidence sources
- `/proc/asound/*` snapshot deltas
- `tinymix` / `amixer` snapshot deltas
- DAPM/debugfs deltas (`/sys/kernel/debug/asoc/*/dapm`)
- `dmesg` telemetry deltas
- playback command completion signal

## Correlation signals
- `pcm_activation`
- `backend_activity`
- `dapm_state_change`
- `mixer_change`
- `playback_completion`
- `route_activation_confidence` (`LOW`/`MEDIUM`/`HIGH`)

## Result interpretation
- success path requires playback completion and route activation evidence.
- missing telemetry is preserved as advisory uncertainty.
- no semantic success is claimed from command exit code alone.
