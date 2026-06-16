# DAPM Graph (Blind v1)

## Widgets
- `IN` (input)
- `SPKR` (speaker endpoint with event callback)

## Routes
- `SPKR <- IN`

## Event behavior
- POST_PMU: apply gain/mode + enable PA path
- PRE_PMD: disable PA + watchdog path cleanly
