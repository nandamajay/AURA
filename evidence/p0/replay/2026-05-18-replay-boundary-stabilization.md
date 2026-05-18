# P0 Replay Consistency Boundary Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `replay-snapshot-drift-under-mutation`
- Discovery reference:
  - `AURA/data/outputs/runtime_discovery/runtime_discovery_20260517T193152Z-kieleu.json`
- Observed issue:
  - Replay returned mutable logs as successful while writes were still in progress.
  - Active replay reads produced non-stable prompt/response counts under concurrent mutation.
  - Finalization boundary was implicit and not enforced.

## Reproduction before fix (runtime)
- Artifact:
  - `AURA/data/outputs/runtime_discovery/replay_boundary_before_replay-boundary-before-323a9775.json`
- Result:
  - `samples_count=108`
  - `all_success_true=true` during mutable writes.
  - `prompt_count_distinct=107` (`min=0`, `max=120`) showing unstable replay boundary.

## Affected subsystem and code paths
- Subsystem: `S3 Knowledge System` replay persistence path
- Code paths:
  - `AURA/workspace/aura-sdk/src/aura_sdk/replay/recorder.py`
  - `AURA/workspace/aura-sdk/src/aura_sdk/replay/replayer.py`
  - `AURA/knowledge/schema/018_task_logs_replay_boundaries.sql`

## Minimal correction implemented
- Added explicit task log state boundary:
  - `recording_state`: `mutable | finalized`
  - `revision` counter
  - `finalized_at`, `snapshot_json`, `snapshot_hash`
- Enforced immutable finalized snapshot semantics:
  - replay only succeeds for `recording_state=finalized`
  - mutable logs return deterministic `INCOMPLETE` with `Task log not finalized`
  - post-finalize writes are rejected by recorder update guard
- Added finalized snapshot integrity verification:
  - output hash and snapshot hash both verified when available
- Added schema migration:
  - `018_task_logs_replay_boundaries.sql`

## Regression validation
- Updated replay tests:
  - `AURA/workspace/aura-sdk/tests/test_replay.py`
- Containerized test run:
  - `25 passed`
  - includes replay + event bus + models + core regression subsets

## Runtime validation after fix
- Artifact:
  - `AURA/data/outputs/runtime_discovery/replay_boundary_after_replay-boundary-after-facd0c8f.json`
- Result:
  - Mutable phase: `success_true_count=0`, `not_finalized_error_count=99`
  - Finalized phase: 20/20 stable replays with
    - `stable_prompt_count_distinct=1`
    - `stable_output_hash_distinct=1`
    - `stable_snapshot_hash_distinct=1`
  - Late mutation after finalize rejected (`late_prompt_ok=false`, `late_response_ok=false`)
  - Corruption detection works (`integrity_ok_after_corruption=false`)

## Runtime API behavior check
- Artifact:
  - `AURA/data/outputs/runtime_discovery/replay_endpoint_boundary_after_replay-endpoint-after-e4554f0a.json`
- Result:
  - Mutable task replay endpoint: `404`
  - Finalized task replay endpoint: `200` with `integrity_ok=true`

## Deterministic impact
- Replay boundary is now explicit and deterministic.
- Concurrent writes are separated from replay via finalized snapshot state.
- Finalized snapshots are immutable from recorder API perspective.

## Replay/audit impact
- Replay semantics changed from "best effort live row read" to "finalized snapshot only".
- This behavior change is intentional and documented in this evidence record.

## Regression risk assessment
- Medium:
  - Mutable/in-flight tasks now return replay not available (404 at API layer) until finalize.
  - Legacy finalized rows without snapshot still replay via compatibility path.

## Rollback strategy
- Revert commit touching replay recorder/replayer + migration 018 + replay tests.
- Rebuild/restart core service.
- Re-run before/after boundary scenarios to confirm behavioral reversion.
