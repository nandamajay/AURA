# Source Trust Classification Report

Date: 2026-05-18

## Runtime Classification Model
- `trusted`
- `bounded-trust`
- `untrusted/manual-review-required`

## Classification Evidence
Source: `evidence/provenance/2026-05-18-source-provenance-runtime-evidence.json`

### Trusted Path
- Input: valid downstream/upstream URLs + commit anchors + maintainer refs.
- Validation result: `trusted`
- Approval allowed via reviewer role in tested flow.

### Bounded-Trust Path
- Input: valid URLs but missing commit anchors.
- Validation result: `bounded-trust`
- Admin override to `trusted` succeeded and produced audit entry.

### Untrusted Path
- Input: invalid downstream URL (`invalid-url`).
- Validation result: `untrusted/manual-review-required`
- Reviewer approval attempt blocked (`403`).
- Approver approval succeeded (`200`).
- `approval_requested` event emitted.

## Override Audit Evidence
- Audit event type: `config.changed`
- Target type: `source_intake`
- After-state includes:
  - previous trust classification
  - new trust classification
  - override reason

## Trust Enforcement Conclusion
- Trust classification is executable and role-gated.
- Untrusted source intake requires higher-role operator approval in runtime.
- Overrides are audit-visible and replay-visible via event stream.
