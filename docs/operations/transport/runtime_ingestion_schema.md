# Runtime Ingestion Schema

## Scope
Contract-only runtime ingestion boundaries for real hardware onboarding. No synthetic payloads are committed in this phase.

## Canonical Event Envelope
- `timestamp`: RFC3339/epoch-normalized capture time
- `source`: ingestion adapter source (`dmesg`, `ftrace`, `trace-cmd`, `procfs`, `debugfs`, `mailbox`, etc.)
- `event_type`: normalized runtime event type
- `subsystem`: ALSA/ASoC/DAPM/SoundWire/DSP/IRQ/clock/regulator
- `lineage_id`: deterministic lineage identifier
- `session_id`: capture session identifier
- `payload`: source-specific structured body

## Required Capture Boundaries
- ALSA traces
- DSP logs
- IPC/mailbox traces
- PCM lifecycle events
- FE/BE topology events
- regulator events
- clock vote traces
- firmware/runtime events

## Governance Rules
- read-only ingestion
- immutable evidence persistence
- fail-closed on missing required fields
- replay lineage must persist for every accepted record
