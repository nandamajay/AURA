# Controlled Downstream-to-Upstream Pilot Conversion Architecture

## Purpose

This layer executes **small, isolated, runtime-backed** pilot transformations
under strict fail-closed governance.

It is designed to:

- generate human-reviewable upstream patch proposals
- reject unsafe or ambiguous transformations by default
- preserve deterministic replay and full lineage persistence
- keep runtime truth and governance as hard gates

## Scope

Pilot mode supports only low-risk categories:

- logging wrapper replacement
- vendor macro normalization
- simple helper abstraction removal
- PCM capability mapping cleanup
- small topology normalization
- static downstream wrapper elimination
- trivial API replacement equivalence
- isolated subsystem utility conversion

## Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/controlled_pilot_conversion.py`
  - `ControlledPilotConversionEngine`
- Persistence:
  - `ControlledPilotConversionRegistry`
- Runner:
  - `scripts/aura-controlled-pilot-conversion.py`

## Governance Model

Default posture is **FAIL_CLOSED**.

Hard blocks include:

- runtime-backed equivalence confidence below threshold
- unresolved unsupported vendor constructs
- cross-subsystem scope in pilot mode
- acceptance simulation threshold failures
- regression containment below threshold
- any governance policy violation (autonomous mutation/patching flags)

Autonomous patch delivery remains disabled in pilot mode.
Human review is always required.

## Deterministic Execution Flow

1. Reason
2. Runtime evidence correlation
3. Translation proposal
4. Acceptance simulation
5. Governance scoring
6. Pilot transformation generation
7. Human review packaging
8. Replay persistence
9. Rollback validation

## Generated Artifacts

- `pilot_conversion_patch.diff`
- `transformation_explainability_report.json`
- `runtime_equivalence_validation.json`
- `upstream_review_package.json`
- `pilot_risk_assessment.json`
- `transformation_lineage.json`
- `rollback_validation_report.json`
- `deterministic_pilot_replay.json`
- `governance_decision_report.json`

## Determinism + Replay Guarantees

- all artifacts carry deterministic fingerprints
- replay state is persisted in cognition registry history
- replay payload can be reconstructed by lineage ID
- rollback sequence is persisted and validated against segment/chunk ordering

## Runtime Truth and Isolation

- runtime evidence is the primary truth input
- plugin adapters are used through contract interfaces
- no target-branching is allowed in core pilot engine
- pilot layer is advisory/governed; no automatic production mutation
