# ADB Runtime Constraints

- No implicit root access.
- No remount or write operations without approval.
- Offline/unauthorized devices must remain UNKNOWN.
- No reconnect storms; limit retries to explicit operator request.
