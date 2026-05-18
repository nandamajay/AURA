# Governance Boundary Assessment

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Phase Results
- phase1_status_counts: `{'200': 4}`
- phase2_status_counts: `{'200': 48}`
- pending_outside_target_after_phase1: `{'media': 12, 'automation': 12, 'research': 12}`
- pending_outside_target_after_phase2: `{'media': 3, 'automation': 3, 'research': 3}`
- status_by_domain: `{'driver': {'passed': 3, 'failed': 3, 'pending': 3, 'in_progress': 3}, 'media': {'passed': 3, 'failed': 3, 'pending': 3, 'in_progress': 3}, 'automation': {'passed': 3, 'failed': 3, 'pending': 3, 'in_progress': 3}, 'research': {'passed': 3, 'failed': 3, 'pending': 3, 'in_progress': 3}}`

## Audit Evidence
- domain-governance audit entries captured: `52`
- audit delta rows (campaign): `52`
- audit delta mismatch (campaign): `0`

## Interpretation
- Proven: phase1 non-target approvals remained pending (no unintended cross-domain mutation).
- Bounded: governance is isolated by ID/patch conventions, not explicit schema partitioning.
- Risk: chronology remains globally interleaved in append-only ledger (expected, but requires filtered views for per-domain ops).
