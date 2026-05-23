# Runtime Evidence Acquisition and Hardware Truth Validation Architecture

## Mission

Acquire live runtime evidence from Qualcomm target platforms (or archived
capture streams), normalize cross-subsystem behavior, and enforce runtime-backed
equivalence governance for transformation safety.

## Inputs

- runtime trace sources:
  - `dmesg`
  - `ftrace`
  - `trace_cmd`
  - `tinymix_state`
  - `procfs_runtime`
  - `debugfs_runtime`
  - `soundwire_runtime`
  - `dsp_mailbox`
  - `irq_runtime`
  - `clocks`
  - `regulators`
  - `ipc_path`
- translation artifacts:
  - `upstream_translation_plan.json`
  - `api_replacement_map.json`
  - `runtime_equivalence_validation.json`
- IPCAT descriptor:
  - `ipcat_hardware_descriptor.json`
- governance state + deterministic replay signal

## Core Responsibilities

- live trace ingestion adapters (read-only)
- IPCAT hardware descriptor ingestion
- runtime topology reconstruction (FE/BE + subsystem graph)
- PCM/DAPM/SoundWire lifecycle capture
- DSP/mailbox synchronization and IRQ ordering capture
- clock/regulator state correlation
- downstream/upstream runtime divergence detection
- runtime-backed equivalence fingerprint generation
- target session persistence and replay
- cross-platform runtime history comparison
- evidence quality scoring and missing-coverage detection

## Required Outputs

- `runtime_equivalence_fingerprint.json`
- `hardware_truth_graph.json`
- `target_runtime_capture.json`
- `downstream_upstream_runtime_diff.json`
- `ipc_topology_map.json`
- `evidence_quality_report.json`
- `runtime_divergence_report.json`
- `target_session_replay.json`

## Governance Gate

Transformations remain blocked unless runtime-backed equivalence confidence is
above the configured threshold and governance posture is fail-closed compliant.

## Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-runtime-evidence-acquisition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id runtime_evidence_acquisition_session_v1 \
  --lineage-id runtime_evidence_acquisition_v1
```

Optional IPCAT source:

```bash
--ipcat-hardware-metadata /path/to/ipcat_hardware_descriptor.json
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_runtime_evidence_acquisition_static.py -q
```
