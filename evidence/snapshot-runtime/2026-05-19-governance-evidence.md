# Governance Evidence

Date: 2026-05-19

## Enforced Governance Controls
- High-risk operations modeled and gated:
  - `transformation_proposal`
  - `lineage_finalization`
- Governance actions are append-only records:
  - `engineering_governance_actions`
- Decisions are audit-visible:
  - `approval.submitted`
  - `approval.granted`
  - `approval.rejected`

## Runtime Evidence
Source:
- `evidence/snapshot-runtime/2026-05-19-snapshot-runtime-evidence.json`

Observed governance sequence:
- transformation request -> approved
- lineage finalization request -> approved

Captured governance rows:
- `transformation_proposal: requested`
- `transformation_proposal: approved`
- `lineage_finalization: requested`
- `lineage_finalization: approved`

## Bypass Protection
Regression coverage:
- `test_approval_bypass_is_blocked_for_lineage_finalization`
- lineage finalization without approved governance action returns `409`
