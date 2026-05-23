# Engineering Investigation Architecture

## Mission

The Engineering Investigation and Query Reasoning Layer enables deterministic,
evidence-backed answers for engineering investigation questions across runtime,
topology, migration, patch, and replay domains.

It preserves:

- runtime truth precedence
- fail-closed governance
- deterministic replay guarantees
- plugin/runtime isolation
- advisory-only behavior

## Query Lifecycle

1. Query ingestion (`engineering_query_engine.py`)
2. Intent + resolver planning (`causality_query_planner.py`)
3. Domain resolver execution:
   - `runtime_question_resolver.py`
   - `migration_question_resolver.py`
   - `topology_question_resolver.py`
   - `patch_reasoning_resolver.py`
   - `replay_evidence_resolver.py`
4. Deterministic synthesis (`investigation_reasoner.py`)
5. Query history + lineage tracking:
   - `engineering_query_history.py`
   - `reasoning_lineage_tracker.py`
6. Session persistence + replay (`investigation_session_registry.py`)

## Deterministic Explanation Model

Every answer entry in `engineering_answer_trace.json` includes:

- `evidence_sources`
- `causality_chain`
- `confidence_score`
- `replay_lineage`
- `governance_state`
- `fail_closed_justification`

This guarantees explanations are traceable and replay-safe.

## Correlation Domains

The engine correlates evidence from:

- semantic cognition
- structural cognition
- runtime truth
- migration lineage
- patch cognition
- incident reconstruction
- evidence fusion
- deterministic replay lineage

## Governance Behavior

Fail-closed conditions include:

- governance policy violations
- insufficient domain evidence
- resolver confidence below threshold
- missing required planned domains

Forbidden behavior:

- hallucinated explanations
- autonomous code/runtime mutation
- autonomous patch generation
- governance bypass

## Generated Artifacts

- `investigation_reasoning_graph.json`
- `engineering_answer_trace.json`
- `causality_resolution_report.json`
- `migration_blocker_reasoning.json`
- `runtime_question_lineage.json`
- `deterministic_investigation_replay.json`
- `engineering_investigation_summary.json`

## Operational Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-engineering-investigation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id engineering_investigation_session_v1 \
  --lineage-id engineering_investigation_v1 \
  --question "What caused this runtime failure?"
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_engineering_investigation_static.py \
  AURA/workspace/aura-sdk/tests/test_runtime_incident_reconstruction_static.py \
  AURA/workspace/aura-sdk/tests/test_runtime_evidence_ingestion_static.py -q
```

## Engineering Impact

This layer improves:

- debugging workflows: direct failure-cause answers with lineage and causality
- regression triage: patch and replay correlation in one deterministic query flow
- migration investigation: fail-closed blocker explanations with evidence basis
- topology validation: route/path mismatch reasoning tied to runtime evidence
- runtime causality analysis: lifecycle and incident signal correlation
- DSP sync debugging: mailbox/sync failure reasoning in query responses
- deterministic engineering replay: reproducible question-answer lineage
