# Unresolved Runtime Gaps

## Mandatory Unknowns (Fail-Closed)
- SoundWire transport runtime topology parity
- MBHC callback parity and jack detection correctness
- Regulator sequencing timing parity
- Calibration ownership runtime continuity
- DAPM route behavior parity
- ALSA control exposure parity
- Runtime PM transition parity

## Why Unknowns Remain
- No hardware runtime trace capture in this phase
- No DSP/runtime lab validation evidence in this phase
- No end-to-end jack insertion/removal telemetry evidence in this phase
- No regulator timing instrumentation evidence in this phase

## Required Evidence to Reduce Unknowns
- Instrumented runtime traces for SDW attach/detach and interrupts
- MBHC event trace corpus with jack/button scenarios
- Regulator on/off ordering timeline captures
- Calibration ownership transition logs with operator approvals
- ALSA control dump + DAPM graph dump diff from both sides
- Runtime PM suspend/resume ordered traces

## Current Policy Decision
- maintain advisory-only status
- maintain runtime-unverified status
- maintain escalation-required status
- prohibit merge-readiness claims
