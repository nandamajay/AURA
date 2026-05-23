# RB3Gen2 Speaker Playback Cognition

## Scope
RB3Gen2 only. No cross-board generalization in this phase.

## Architecture boundary
- Linux side: governance authority, topology cognition, playback planning, failure reasoning.
- Windows side: execute-only worker for approved operations (`adb shell`, optional `adb push`).
- Target: runtime evidence source.

## Playback cognition depth
- overlay detection and ambiguity control
- PCM inference from `/proc/asound/pcm`
- backend/frontend mapping from DTS/DTSI routing evidence
- mixer dependency sequencing as procedural activation flow
- codec activation candidate reasoning from static topology
- WAV selection and deployment planning
- runtime validation correlation (PCM, DAPM, dmesg, mixer deltas)
- failure explanation with explicit evidence gaps

## Governance guarantees
- fail-closed classification
- no hallucinated mixer writes
- no hallucinated asset selection
- no unsupported execution assumptions
- advisory-only claims only
