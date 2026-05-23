# Command Normalization Spec

## Scope
Linux governance emits canonical target commands only.
Windows worker executes normalized commands only via transport expansion rules.

## Canonical SAFE_READ commands
- `getprop ro.build.fingerprint`
- `cat /proc/version`
- `cat /proc/asound/cards`
- `echo AURA_BRIDGE_PING` (handshake only)

## Canonical governed write operation (operator-approved only)
- `AURA_ADB_PUSH <bridge_relative_path> <target_path> <sha256> <overwrite_policy>`
- `AURA_PLAYBACK_APLAY <(plug)hw:x,y> <target_path>`
- `AURA_PLAYBACK_TINYPLAY <target_path> <card> <device>`
- `AURA_TINYMIX_SET <control_id> <value>`
- `AURA_AMIXER_CSET numid=<id> <value>`
- `AURA_AMIXER_NAME_SET <base64url(control_name)> <value>`
- `AURA_ADB_RM <target_path>`
- accepted only when Linux submitter is invoked with `--allow-write-ops`
- accepted only when Windows worker runs with write ops enabled and request execution mode is `governed_write_approved`

## Normalization rules
- trim leading/trailing whitespace
- collapse repeated internal whitespace to one space
- preserve command token order
- reject empty command after normalization

## Forbidden patterns
- shell chaining/operators: `;`, `&&`, `||`, `` ` ``, `$(`, `>`, `<`
- transport nesting: `adb ...`, `adb.exe ...`, `shell ...`
- wrapper leakage: `sh -c`, `bash -c`, `cmd /c`, `powershell ...`

## Governance posture
- non-canonical or forbidden command => `REJECTED`
- governed write operation without explicit enablement => `REJECTED`
- no parity/merge-readiness claims
- advisory-only semantics preserved
