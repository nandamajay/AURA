# RB3 WAV Asset Intelligence

## WAV registry
Registry path:
- `AURA/workspace/aura-sdk/src/aura_sdk/transport/rb3_wav_asset_registry.json`

Each entry includes:
- `asset_id`
- `repository_path`
- `bridge_relative_path`
- `sample_rate_hz`
- `channels`
- `format`
- `intended_playback_path`
- `validation_purpose`

## Automatic deployment model
1. Linux selects compatible asset from registry.
2. Linux verifies source file checksum.
3. Linux stages asset to bridge share (`bridge/<bridge_relative_path>`).
4. Linux emits governed push operation command:
   - `AURA_ADB_PUSH <bridge_relative_path> <target_path> <sha256> <overwrite_policy>`
5. Windows worker executes `adb push` only when:
   - write ops enabled on worker
   - request execution mode is `governed_write_approved`
6. Windows verifies target checksum and preserves immutable traces.

## Overwrite protection
- `no_overwrite`: deployment rejected if target already exists.
- `allow_overwrite`: overwrite is allowed with checksum verification.

## Safety posture
- push operation always requires operator-approved execution mode
- unsupported/malformed deployment operations are rejected fail-closed
- no implicit fallback to unverified assets
