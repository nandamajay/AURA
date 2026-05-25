# Lifecycle Execution Report

Generated: `2026-05-19T06:34:08.589894+00:00`

## Runtime Identity
- intake_id: `4a94e7ef986e6f54ce466a247aada14b`
- workflow_id: `28f5d02bea8699fefd6335f3f7878b39`
- task_id: `634d52ad-2301-42b7-9e1b-f47bf0e1739e`
- source repo: `ssh://review-android.quicinc.com:29418/platform/vendor/qcom/opensource/audio-kernel-ar`
- source branch: `audio-kernel-cmn.lnx.0.0`
- source commit: `466891703077f54117390782cce636830ad8ae1c`

## Required Workflow Lifecycle (Executed)
1. `source_intake`: completed via `/api/v1/provenance/sources/register`
2. `snapshot_frozen`: completed via source + engineering snapshots
3. `dependency_discovery`: recorded in replay execution steps + patch_transform lineage payload refs
4. `analysis`: recorded in `transition_patch_analysis` and mapping report generation
5. `transform_planning`: recorded in `transition_transformation_proposal`
6. `validation`: executed via engineering validation endpoint (`status=failed`)
7. `governance_review`: request+decision persisted in governance actions table
8. `replay_finalization`: reconstruction + lineage finalize + replay_evidence lineage persisted

## Detached Execution Guard
- probe result: status `400`
- detail: `{'detail': 'detached_engineering_execution_forbidden:missing=intake_id,snapshot_id,provenance_lineage_hash,workflow_id'}`

## Snapshot Integrity Anchors
- source_snapshot_id/hash: `d278ec4e62dd40895af9c0dccae2c059` / `9e203382e1c42231be948d66d706c59ecf44ef6a696b72612d3c4400730645ca`
- engineering_snapshot_id/hash: `08519996347892514066537e992917e1` / `891ebfd380fba2d8c89aef4ef02a56a3e26f542c4b4814e9fa6e7400d259d82b`
- workflow_reconstruction_hash: `1e65c354569412f12624d2906c4f58fd89676cc2566e9adc7d7b2ffd0d103ffe`
- source_reconstruction_hash: `e861f1ab5ff58569dc26384f1a69c719658c788cf2d861a109de958eca365f40`

## Raw Evidence
- `raw/runtime_lifecycle_trace.json`
- `raw/workflow_events_rows.json`
- `raw/source_lineage_rows.json`
