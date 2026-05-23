# Subsystem Discovery Flow

## Qualcomm audio discovery
- ALSA topology parser from `cat /proc/asound/cards`
- PCM parser from `cat /proc/asound/pcm`
- `tinymix` and `amixer` control evidence parsing when probes are available
- DAPM/debugfs evidence parsing when available (`/sys/kernel/debug/asoc`)
- RB3Gen2 detector from card/platform markers (`rb3gen2`, `qcs6490`)
- DSP/QDSP detector from runtime strings (`qdsp`, `adsp`, `q6`, `hexagon`)
- audio subsystem evidence graph emitted in fingerprint output
- DTS/DTSI parser for `dai-link`, `qcom,audio-routing`, SoundWire and codec nodes
- runtime + static correlation into playback/capture procedural workflows

## Discovery lifecycle
1. Probe commands execute (safe read only)
2. Parser extracts subsystem signals
3. Capability states computed
4. DTS/DTSI static context parsed and correlated
5. Cognition mode selected (`Known`, `Learning`, `Discovery`)
6. Adaptive procedural plan generated
7. Unsupported/ambiguous paths preserved as advisory evidence
