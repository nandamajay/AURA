# PM Recommendation: WCD Rule-Pack Checker Gate Integration

Generated: 2026-06-20

## 1. Should the checker be integrated into canonical gate now?
Yes, but only as an optional add-on with non-default activation and no immediate blocking behavior.

## 2. Should it be advisory, warn, or blocking?
- Immediate recommendation: `advisory` for initial integration.
- Next step after regression completion: `warn` mode for WCD family.
- `blocking` mode should be deferred until maturity criteria in blocking proposal are met.

## 3. Which checks are mature enough?
Most mature:
- Rule file parse/schema validation.
- Artifact presence and lineage existence inference.
- Existing derivation-risk surfacing from canonical verifier/anti-copy artifacts.
- Gate/build status summarization.

## 4. Which checks are too heuristic?
Too heuristic for blocking today:
- Vendor-token scan.
- LA/LE terminology scan.
- Runtime-evidence filename/phrase detection.
- Hidden-target audit where allowlist schema is incomplete.

## 5. What must be tested first?
- Full matrix from `regression_test_plan.json`.
- Mode policy mapping correctness (`off/advisory/warn/blocking`).
- FAIL_CLOSED_OK non-blocking invariant.
- Known fixtures:
  - WCD9378 A.1 -> expected WARN profile.
  - WCD939x variant_0 -> expected PASS profile.
  - WCD939x variant_1 -> expected WARN profile.

## 6. How should this affect WCD9378 after Monday?
- It should improve governance observability and consistency for post-Monday evidence ingestion.
- It must not auto-unblock runtime-sensitive WCD9378 decisions.
- Runtime blockers remain evidence-gated and fail-closed until explicit hardware logs close them.

## 7. What is the PM verdict?
`INTEGRATE_WARN_MODE_AFTER_TESTS`
