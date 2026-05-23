# ADB Timeout Matrix

| Operation | Timeout (ms) |
|---|---:|
| `adb devices` | 5,000 |
| `adb shell <read>` | 10,000 |
| `adb pull` | 10,000 |
| `adb push` | 10,000 |
| `logcat -d` | 10,000 |
| `dmesg` | 10,000 |

Timeouts are mandatory and fail closed.
