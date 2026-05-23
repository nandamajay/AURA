# ADB Shell Boundary Rules

## Rule 1
Linux governance must never emit `adb ...` in `approved_commands`.

## Rule 2
Windows worker must execute only `adb shell <normalized_command>` expansion.

## Rule 2a
For governed asset deployment, Windows worker may execute only:
- `adb push <bridge_asset> <target_path>`
- `adb shell sha256sum <target_path>` (or `toybox sha256sum` fallback)
- target path restricted to `/data/local/tmp/aura/audio/...`
- overwrite policy enforced fail-closed

## Rule 2b
For controlled runtime playback validation, Windows worker may execute wrapper-expanded commands only:
- `adb shell tinymix <control_id> <value>`
- `adb shell amixer cset numid=<id> <value>`
- `adb shell amixer -c 0 cset iface=MIXER,name='<decoded_name>' '<value>'`
- `adb shell aplay -D <(plug)hw:x,y> <target_path>`
- `adb shell tinyplay <target_path> -D <card> -d <device>`
- `adb shell rm -f <target_path>`

## Rule 3
Windows worker must not prepend shell wrappers (`sh -c`, `bash -c`, `cmd /c`) to canonical commands.

## Rule 4
Every command execution must preserve:
- normalized command
- raw executor invocation
- exit code
- timestamps

## Rule 5
Any boundary violation is fail-closed:
- `REJECTED` or `INVALID` depending on violation type.

## Governance note
Results remain advisory-only. No runtime parity or merge-readiness claims.
