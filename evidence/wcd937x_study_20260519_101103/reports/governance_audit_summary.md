# Governance and Audit Summary

## Governance Actions
- workflow_id: `d285331f26c70c20ac81f9ed3b273279`
- total actions: `4`
- id=1 operation=`transformation_proposal` status=`requested` reason=`operator_governance_review`
- id=2 operation=`transformation_proposal` status=`approved` reason=`bounded_override_validation_tools_unavailable_for_full_signal`
- id=3 operation=`lineage_finalization` status=`requested` reason=`freeze_replay_lineage`
- id=4 operation=`lineage_finalization` status=`approved` reason=`lineage_finalization_approved`

## Audit Ledger Chronology
- total audit rows: `17`
- first event: `config.changed` on `engineering_snapshot` `6070de47ce135ad890e491ae85d9bff7`
- last event: `task.progress` on `engineering_workflow` `d285331f26c70c20ac81f9ed3b273279`

## Key Governance Outcome
- Transformation approved with explicit reason despite failed validation signal:
  `bounded_override_validation_tools_unavailable_for_full_signal`
- Lineage finalization separately requested and approved before finalization call.

## Evidence
- `raw/governance_actions_rows.json`
- `raw/audit_ledger_rows.json`
- `raw/runtime_lifecycle_trace.json`

## Evidence Linking
- evidence links recorded on workflow: `10`
