# Safe Runtime Command Log

| Transport | Command | Allowed | Reason |
|---|---|---|---|
| `adb` | `getprop ro.build.fingerprint` | `True` | `allowlisted_safe_read` |
| `adb` | `getprop ro.product.device` | `True` | `allowlisted_safe_read` |
| `adb` | `cat /proc/version` | `True` | `allowlisted_safe_read` |
| `adb` | `cat /proc/asound/cards` | `True` | `allowlisted_safe_read` |
| `adb` | `cat /proc/asound/pcm` | `True` | `allowlisted_safe_read` |
| `adb` | `dmesg | tail -50` | `True` | `allowlisted_safe_read` |
