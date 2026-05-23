# RB3 Downstream-to-Upstream Validation Workflow

## Objective
Use RB3 runtime evidence to drive deterministic procedural cognition and then feed validated learnings upstream into planning memory.

## Flow
1. Build static topology context (DTS/DTSI, overlays, SoundWire markers).
2. Build runtime fingerprint from transport evidence (`/proc/asound`, mixer/debugfs, dmesg).
3. Generate speaker playback workflow plan (overlay, route, PCM, WAV deployment, validation telemetry).
4. Execute only approved operations via Windows worker.
5. Correlate runtime telemetry for route activation confidence.
6. Record procedural outcomes (success/failure, quirks, constraints, recovery patterns).
7. Reuse memory in next run to improve deterministic planning.

## Governance constraints
- no unsupported writes
- no hallucinated assets/routes
- evidence-backed transitions only
- fail-closed on ambiguity
