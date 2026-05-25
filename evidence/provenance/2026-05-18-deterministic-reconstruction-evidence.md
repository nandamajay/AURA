# Deterministic Reconstruction Evidence

Date: 2026-05-18

## Test Scenario
- Register source intake.
- Validate + classify.
- Approve intake.
- Create replay snapshot.
- Record retry/retry/rebase lineage.
- Reconstruct intake state twice without mutation.

## Runtime Outputs
Evidence file: `evidence/provenance/2026-05-18-source-provenance-runtime-evidence.json`

- Reconstruction hash run #1:
  - `809ff82d7c9c056bea901aba94e4f40d698d6fda2fe0f440fd58574bb0c8e88c`
- Reconstruction hash run #2:
  - `809ff82d7c9c056bea901aba94e4f40d698d6fda2fe0f440fd58574bb0c8e88c`
- Equality:
  - `true`

## Duplicate Intake Determinism Check
- Semantically identical source intake re-registration produced:
  - `409 duplicate_source_intake`
- Confirms canonical-hash deduplication path.

## Reconstruction Integrity Conclusion
- Intake reconstruction is deterministic under fixed persisted state.
- Replay-critical identity is anchored by:
  - canonical intake hash
  - append-only event stream
  - append-only lineage chain
  - immutable snapshot hash
