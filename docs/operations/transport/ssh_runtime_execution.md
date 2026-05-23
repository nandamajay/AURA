# SSH Runtime Execution

## Rules
- Use bounded execution with explicit timeouts
- No persistent shell mutations
- No destructive sudo operations

## Read-Only Examples
- `uname -a`
- `cat /proc/asound/cards`
- `dmesg | tail -n 200`
