# WCD9378 Blocker Burndown 01 — Datasheet Delta Summary

Generated: 2026-06-20 (audit-only delta, no source modifications)

## 1. What did the real WCD9378 datasheet change?
- It materially strengthened silicon identity evidence for WCD9378:
  - Device-specific naming and product framing (page 1).
  - CHIP_ID byte table for WCD9378 sample types (Table 4-3, page 34).
- It confirmed hardware-level reset/supply/SWR topology details:
  - RESET_N pin and supply rails (page 13, page 15).
  - SoundWire protocol generation statement (SoundWire v1.2.1, page 29).
- It did **not** provide software-visible register map/base details.

## 2. Which blockers are now resolved?
- None moved from fail-closed to fully resolved solely by datasheet.
- Several items improved to partial confidence (identity/supply/reset architecture), but remained non-actionable for conversion start.

## 3. Which blockers remain fail-closed?
- Exact SDW identity tuple for Linux (`SDW_SLAVE_ENTRY` part-id value for WCD9378).
- Proposed compatible string `sdw20217011000`.
- Fallback compatibility policy with `qcom,wcd9370-codec` / `qcom,wcd9375-codec`.
- `qcom,swr-tx-port-params` necessity and upstream representation.
- Class-H base/version strategy in `wcd-clsh-v2`.

## 4. Does the datasheet justify WCD9378 SDW identity?
- **No (not fully).**
- It gives CHIP_ID bytes (page 34) and SWR protocol level (page 29), but no explicit mapping to Linux SDW manufacturer/part-id tuples.

## 5. Does the datasheet justify WCD9378 paging?
- **No (not directly).**
- No register-address or paging-register documentation was found.
- Existing paging confidence still comes from downstream/upstream code analysis, not datasheet text.

## 6. Does the datasheet justify Class-H dynamic base/version?
- **No.**
- Datasheet confirms Class-H functional/performance behavior (pages 24-26), but provides no Class-H register-domain/base mapping needed to decide enum/base abstraction.

## 7. Can WCD9378 conversion start now?
- **NO-GO**.
- Blocking fail-closed items remain on SDW identity and Class-H base/version strategy; runtime evidence remains missing.

## 8. If yes, what narrow first patch series is allowed?
- Not applicable for full conversion start.
- At most, pre-conversion documentation/binding prep can proceed without asserting unresolved SDW/Class-H claims.

## 9. If no, what evidence is still missing?
1. Hardware-enumerated SoundWire manufacturer/part ID tuple for WCD9378 (sufficient for SDW driver ID and DT compatible derivation).
2. Runtime traces proving high-address/paging behavior on upstream Linux SDW path.
3. Runtime/register traces proving whether existing `WCD937X` class-h path is sufficient or a WCD9378-specific class-h treatment is required.
4. Deterministic proof for `qcom,swr-tx-port-params` (required vs removable/mappable).
