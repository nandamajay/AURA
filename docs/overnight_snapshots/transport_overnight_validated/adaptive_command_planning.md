# Adaptive Command Planning

## Strategy
- Android strategy candidates: `getprop`, `logcat`, `dumpsys`
- Embedded Linux strategy candidates: `uname`, `procfs`, `dmesg`, `lsmod`
- QEMU enrichers: `cat /proc/cpuinfo`
- Qualcomm enrichers: `cat /proc/asound/pcm`, `tinymix`, `amixer`, `debugfs/dapm` probes

## Selection rule
- Command selected only when required capability is `SUPPORTED`.
- `UNSUPPORTED` and `UNKNOWN` commands are skipped with explicit reason.
- No silent fallback and no implicit wrapper substitution.
- Procedural playback/capture planning is generated only from validated static/runtime evidence.
- Mixer mutation paths remain blocked when mixer dependency confidence is not sufficient.

## Procedural audio cognition extension
- `Known Mode`: resolved overlay/target and strong runtime signal.
- `Learning Mode`: targeted operator questions required before mutation-capable steps.
- `Discovery Mode`: collect-only planning when runtime evidence is insufficient.
- DTS/DTSI (`qcom,audio-routing`, dai-links, codec nodes) is correlated with runtime (`/proc/asound`, mixer/debugfs evidence when available).

## Governance
- Unsupported command execution evidence remains in lineage.
- Classification remains advisory/unknown fail-closed when capability confidence is incomplete.
