# Capability Matrix

Capability states are tri-state:
- `SUPPORTED`
- `UNSUPPORTED`
- `UNKNOWN`

| Capability | Probe commands |
|---|---|
| supports_getprop | getprop ro.build.fingerprint |
| supports_logcat | logcat -d -t 200 |
| supports_procfs | cat /proc/version, cat /proc/asound/cards |
| supports_uname | uname -a |
| supports_dmesg | dmesg |
| supports_lsmod | lsmod |
| supports_tinymix | tinymix |
| supports_systemd | systemctl --version |
| supports_dumpsys | dumpsys media.audio_flinger |
| supports_debugfs | ls /sys/kernel/debug, ls /sys/kernel/debug/asoc |

Rules:
- any `not found` or non-zero exit evidence => `UNSUPPORTED`
- absent probe evidence => `UNKNOWN`
