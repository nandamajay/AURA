# SoundWire Patterns (Promoted)

## Pattern 1: SDW-native stream lifecycle in DAI ops
- Confidence: HIGH_CONFIDENCE
- Problem: vendor bus abstractions are not directly acceptable upstream.
- Accepted solution: `sdw_stream_add_slave/remove_slave` with SDW driver ownership.
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`
- Maintainers involved: Pierre-Louis Bossart review signal (wsa883x), ALSA acceptance path
- Acceptance rate: 3/3 SDW drivers

## Pattern 2: Split codec logic from SDW transport logic when needed
- Confidence: MEDIUM_CONFIDENCE
- Evidence drivers: `wcd938x` (explicit core+sdw split), `wsa883x/wsa884x` (SDW driver-centric codec)
- Acceptance rate: 3/3 SDW drivers
