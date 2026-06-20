# PM Rule Promotion Summary: WCD Codec Family Rule Promotion 01

Generated: 2026-06-20

## 1. What did the transfer experiment prove?
- WCD938x learning transferred to WCD939x reconstruction with measurable quality improvement.
- Variant 0 score: 41.78 (PASS), Variant 1 score: 60.76 (WARN), delta: +18.98.
- Improvements were meaningful across function/API/DAPM/lifecycle/include dimensions.

## 2. What did it not prove?
- It did not prove runtime behavior correctness.
- It did not prove that LA-heavy reconstruction is safe; derivation warnings increased.
- It did not remove the need for hardware evidence in SDW identity/paging/Class-H decisions.

## 3. Which rules are promoted?
Promoted (`PROMOTE_NOW` or `PROMOTE_WITH_CONDITIONS`) include:
- LE architecture split and LA-content/LE-structure discipline.
- Hidden-target experiment discipline and lineage coverage.
- SoundWire fail-closed identity policy.
- Regmap/regcache caution rules.
- DAPM mapping discipline with anti-copy controls.
- MBHC/Class-H fail-closed integration rules.
- Reset workaround rejection.
- Vendor elimination with stronger gate conditions.
- DTS/schema/evidence separation.
- Runtime evidence gating and PM non-claims policy.

## 4. Which rules are quarantined/rejected?
- Quarantined: WCD-FAMILY-RULE-012 pending stronger vendor-regression and anti-copy enforcement.
- Learn-only: WCD-FAMILY-RULE-008 (IRQ normalization) due NO_EFFECT and insufficient validation evidence.
- Rejected: LA-heavy score-maximization heuristics and speculative runtime synthesis heuristics.

## 5. What should be enforced by tools vs prompts?
Tool enforcement (gate/scorer/verifier):
- Vendor-elimination regression guard.
- Downstream derivation warning confidence penalties.
- Hidden-target audit and lineage coverage checks.
- Runtime-sensitive fail-closed status change checker.

Prompt/checklist/PM enforcement:
- LA/LE terminology consistency.
- DT normalization mapping table and evidence schema completeness.
- Explicit PM "must not claim" section while blockers remain.

## 6. What changes for WCD9378?
- Governance and checklist quality improve immediately.
- Runtime-sensitive blocker status does not change without Monday evidence.
- WCD9378 remains paused for runtime claims.

## 7. What remains blocked until Monday?
- SDW numeric identity and compatible confirmation.
- SDW paging runtime/controller-path proof.
- Class-H base/version runtime confirmation.
- Playback/capture/mute runtime validation and board DTS finalization evidence.

## 8. Should WCD939x transfer validation be considered successful?
- Yes, with caveats. Learning transfer is validated for structural quality gains, but must be constrained by stronger anti-copy and vendor-elimination guardrails.

## 9. Should we do more family transfer experiments?
- Yes. Continue with strict hidden-target control and upgraded anti-copy/vendor-regression governance.

## 10. What is the PM verdict?
`PROMOTE_VALIDATED_RULES_WITH_GUARDRAILS`
