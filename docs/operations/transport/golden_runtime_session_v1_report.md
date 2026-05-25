# GOLDEN_RUNTIME_SESSION_V1

## Classification
- classification: `FAIL_CLOSED`
- fail_reasons: `route_not_stable, irq_not_active, dapm_not_converged, playback_lifecycle_incomplete, playback_write_phase_failure`
- blockers: `governance:route_not_stable; governance:irq_not_active; governance:dapm_not_converged; governance:playback_lifecycle_incomplete; governance:playback_write_phase_failure; playback_attempts_exhausted:plughw:0,0:aplay: main:831: audio open error: Invalid argument | hw:0,0:aplay: main:831: audio open error: Invalid argument | plughw:0,2:aplay: main:831: audio open error: Invalid argument | hw:0,2:aplay: main:831: audio open error: Invalid argument | plughw:0,3:aplay: main:831: audio open error: Invalid argument | hw:0,3:aplay: main:831: audio open error: Invalid argument | default:executor_command_trace_length_mismatch | sysdefault:executor_command_trace_length_mismatch; dapm_widget_states_not_extracted_from_runtime; during_window_metrics_derived_from_playback_trace_not_concurrent_sampling; dts_lineage_partial_due_bridge_allowlist_proc_device_tree_unavailable`

## Hardware Discovery
- kernel: `Linux qemuarm64 7.1.0-rc2-next-20260508-00007-gd7f4b2036195 #39 SMP PREEMPT Mon May 18 13:07:23 +0530 2026 aarch64 GNU/Linux`
- sound_cards: `1`
- pcm_entries: `4`
- dapm_widgets: `0`

## Route Inference
- speaker_alsa_device: `hw:0,0`
- headphone_alsa_device: `hw:0,0`
- confidence: `MEDIUM`
- inferred_mixer_controls: `57`

## Playback Observability
- playback_exit_code: `32`
- irq_audio_deltas: `0`
- dmesg_delta_lines: `0`
- dapm_changes: `0`

## Replay
- runtime_sequence_fingerprint: `5d88d4e58bf2fbe3f03dbdd0fc03ebbc718ebda2ffac5bcc4921f5e964742d09`
- deterministic_replay_fingerprint: `b281b227f81c144077da3d0735d7c49684fb0430d16e7149620226218444f8a1`

## Artifacts
- golden_session: `/workspace/docs/operations/transport/golden_runtime_session_v1.json`
- governance: `/workspace/docs/operations/transport/golden_runtime_session_v1_governance.json`
- hardware_discovery: `/workspace/docs/operations/transport/golden_runtime_session_v1_hardware_discovery.json`
- live_playback_observability: `/workspace/docs/operations/transport/golden_runtime_session_v1_live_playback_observability.json`
- replay_artifact: `/workspace/docs/operations/transport/golden_runtime_session_v1_replay.json`
- report: `/workspace/docs/operations/transport/golden_runtime_session_v1_report.md`
- route_inference: `/workspace/docs/operations/transport/golden_runtime_session_v1_route_inference.json`
- temporal_causal_graph: `/workspace/docs/operations/transport/golden_runtime_session_v1_temporal_causal_graph.json`
