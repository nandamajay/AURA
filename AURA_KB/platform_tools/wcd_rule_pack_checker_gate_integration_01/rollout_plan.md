# Rollout Plan: Rule-Pack Checker -> Canonical Gate Add-on

Generated: 2026-06-20

## Phase 1: Keep Prototype Standalone
- Entry criteria: prototype checker and tests pass on baseline fixtures.
- Exit criteria: stable reports for WCD9378 A.1, WCD939x variant_0, variant_1.
- Rollback plan: continue standalone usage only; no gate coupling.
- Owner role: Tools Engineer + PM reviewer.

## Phase 2: Add Non-blocking Gate Advisory Mode
- Entry criteria: integration patch prepared with additive CLI and schema fields only.
- Exit criteria: gate can invoke checker in advisory mode with zero verdict mutation.
- Rollback plan: disable via `--rule-pack-mode off` and keep checker external.
- Owner role: Gate Maintainer.

## Phase 3: Run on Historical Conversions
- Entry criteria: advisory mode merged behind explicit flags.
- Exit criteria: replay suite across historical WCD runs with archived checker/gate artifacts.
- Rollback plan: stop advisory invocation and collect offline checker reports.
- Owner role: Validation Engineer.

## Phase 4: Tune False Positives
- Entry criteria: replay outputs identify noisy checks and failure classes.
- Exit criteria: heuristic noise reduced with documented thresholds and exceptions.
- Rollback plan: demote noisy checks to INFO/advisory only.
- Owner role: PM + Verifier Maintainer.

## Phase 5: Enable Warn Mode for WCD Family Only
- Entry criteria: regression plan coverage complete; advisory stability proven.
- Exit criteria: warn mode emits predictable WARN effects for checker WARN/FAIL without blocking.
- Rollback plan: revert to advisory mode immediately.
- Owner role: Gate Maintainer + PM approver.

## Phase 6: Consider Blocking Mode for Narrow Criteria
- Entry criteria: blocking candidates validated (rule parse failure, hidden-target violations, mature derivation criteria).
- Exit criteria: narrow BLOCK criteria enabled with low false-positive rates.
- Rollback plan: disable blocking mode and keep warn/advisory while triaging false blocks.
- Owner role: Governance Owner.

## Phase 7: Generalize Rule-Pack Framework Beyond WCD
- Entry criteria: WCD integration stable across cycles and policy proven.
- Exit criteria: family-agnostic rule-pack plugin contract published with cross-family pilots.
- Rollback plan: retain WCD-only support and postpone generalization.
- Owner role: Platform Architecture Lead.
