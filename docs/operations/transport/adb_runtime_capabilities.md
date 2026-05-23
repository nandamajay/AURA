# ADB Runtime Capabilities

## Supported (Read-First)
- `adb devices`
- `adb shell <command>` for read-only commands
- `adb pull`
- `adb push` (operator approval required)

## Read-Only Command Examples
- `cat /proc/asound/*`
- `dmesg`
- `logcat -d`
- `dumpsys media.audio_flinger`

## Constraints
- Device identity must be verified.
- Unauthorized/offline device states must be preserved as UNKNOWN.
- No root assumption.
