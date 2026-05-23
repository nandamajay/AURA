# Runtime Cognition Architecture

## Trust boundary
- Linux: governance authority + cognition + planning
- Windows: execution-only worker
- Target: evidence source

## Cognition components
- `environment_classifier.py`
- `target_fingerprint_engine.py`
- `command_planner.py`
- `audio_runtime_cognition.py`
- `dts_audio_cognition.py`
- `rb3_playback_cognition.py`
- `rb3_wav_asset_registry.json`
- `runtime_capability_graph.py`
- `capability_registry.json`

## Cognition modes
- `Known Mode`: high-confidence runtime + resolved target/overlay selection
- `Learning Mode`: confidence gaps exist; targeted subsystem questions are mandatory
- `Discovery Mode`: runtime audio evidence is insufficient; collect-only planning

## Procedural workflow cognition
- playback workflow templates with sequence gates
- capture workflow templates with unresolved-target safeguards
- mixer dependency graph generation from `qcom,audio-routing` + runtime PCM evidence
- wav asset requirement declaration for any playback/capture plan
- no mixer-path hallucination; unresolved paths remain explicit `UNRESOLVED`

## Static + runtime correlation
- Static inputs:
  - DTS/DTSI includes and overlay inheritance
  - sound card nodes
  - dai-link and backend/frontend route signals
  - `qcom,audio-routing`
  - SoundWire markers and codec nodes
- Runtime inputs:
  - `/proc/asound/cards`
  - `/proc/asound/pcm`
  - `tinymix` (if available)
  - `amixer` (if available)
  - debugfs/DAPM evidence (if available)
  - dmesg markers for DSP/QDSP signals

## Data flow
1. Linux sends canonical probe commands.
2. Windows executes `adb.exe shell <normalized_command>` only.
3. Windows returns immutable response with command traces.
4. Linux builds fingerprint + capability graph.
5. Linux parses DTS/DTSI audio context and correlates runtime evidence.
6. Linux planner emits adaptive procedural workflows (playback/capture) and targeted questions.
7. Linux preserves immutable lineage with advisory-only claims.

## Safety invariants
- fail-closed classifications
- immutable request/response evidence
- replay protection preserved
- no shell-side policy decisions on Windows worker
- no runtime mutation in cognition phase
- no parity/merge claims
