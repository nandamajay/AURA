# Subsystem-Aware Audio Cognition Workflows

## Scope
This layer upgrades AURA from command dispatch to governed audio cognition.
Linux remains authoritative for policy, interpretation, and planning.
Windows remains execution-only and does not perform semantic decisions.

## Workflow outputs
- playback workflow templates
- capture workflow templates
- mixer dependency graph
- runtime audio knowledge graph
- targeted questions when ambiguity exists

## Cognition modes
- Known Mode
  - high confidence runtime evidence
  - target + overlay selection resolved
  - workflow template can be emitted with minimal clarifications
- Learning Mode
  - confidence gaps and/or route ambiguity
  - targeted questions required before mutation-capable workflow steps
  - no mixer path assumptions
- Discovery Mode
  - insufficient runtime subsystem evidence
  - collect-only posture with unresolved fields preserved

## Learning mode question policy
- request overlay/config selection when active overlay is uncertain
- request playback target selection (`speaker`, `headset`, `bt`, etc.) when ambiguous
- request WAV asset and format requirements before playback template finalization
- preserve unanswered fields as `UNRESOLVED`

## Governance constraints
- fail-closed behavior preserved
- immutable lineage preserved
- normalized execution preserved
- advisory-only claims only
  - no runtime parity claims
  - no behavioral equivalence claims
  - no merge-readiness claims
