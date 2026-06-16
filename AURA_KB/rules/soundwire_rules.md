# SoundWire Rules (Promoted)

## Rule 1: Upstream path should use generic SDW lifecycle APIs
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers + subsystem requirement
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`
- Evidence files:
  - `drivers/wsa883x/architecture.md`
  - `drivers/wsa884x/architecture.md`
  - `drivers/wcd938x/architecture.md`

## Rule 2: Model codec core and SDW transport ownership cleanly
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence:
  - WCD938x split (`wcd938x.c` + `wcd938x-sdw.c`) in `drivers/wcd938x/architecture.md`
  - WSA883x/WSA884x SDW codec model in `drivers/wsa883x/architecture.md`, `drivers/wsa884x/architecture.md`
