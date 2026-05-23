# UART Runtime Capture

## Goals
- Non-destructive log capture
- Prompt synchronization before any command
- Kernel panic signature detection

## Safety
- Avoid infinite reads
- Preserve partial output on disconnect
- No write commands without approval
