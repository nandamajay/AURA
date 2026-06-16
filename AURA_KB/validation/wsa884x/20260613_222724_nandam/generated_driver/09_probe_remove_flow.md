# Probe/Remove Flow (Blind v1)

## Probe
1. Allocate private state
2. Acquire regulators + optional reset/powerdown gpio
3. Init regmap
4. Configure SDW properties
5. Initialize runtime PM
6. Register ASoC component + DAI

## Remove
1. Unregister runtime resources
2. Disable regulators and release GPIO state
3. Cleanup debug/proc resources if present
