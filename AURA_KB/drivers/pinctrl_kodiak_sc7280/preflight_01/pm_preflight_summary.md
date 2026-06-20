# PM Preflight Summary: Kodiak/SC7280 TLMM Pinctrl Generalization Pilot

Generated: 2026-06-20

## 1. Is Kodiak/SC7280 TLMM pinctrl viable as a non-audio pilot?
Conditionally yes as a domain, but not yet runnable with current input package.

## 2. What exact LA source exists?
No exact LA TLMM donor source was found for Kodiak/SC7280/QCM6490/QCS6490/SM7325 in provided downstream trees. Only LA audio pinctrl helpers (`pinctrl-lpi.c`, `pinctrl-wcd.c`) exist and are not valid TLMM donor files.

## 3. What exact LE target should be hidden?
`track_b_corpora/linux-next/drivers/pinctrl/qcom/pinctrl-sc7280.c` is the best LE hidden target candidate.

## 4. What relative skeleton should be used?
Primary relative skeleton: `track_b_corpora/linux-next/drivers/pinctrl/qcom/pinctrl-sc7180.c`.
Secondary candidates for sensitivity checks: `pinctrl-sm6350.c`, `pinctrl-sc8180x.c`.

## 5. Is current scoring/gate adequate?
Partially. Gate/verifier are usable generically. Current scorer is audio-biased and incomplete for pinctrl semantics.

## 6. What new pinctrl-specific scorer/gate support is needed?
Add pinctrl-focused static scoring for pin table coverage, group coverage, function-group mapping, wake IRQ mapping, reserved ranges, compatible alignment, and Kconfig/Makefile alignment. Keep anti-copy/lineage/hidden-target checks in canonical gate.

## 7. Should A/B/C conversion variants start now?
No. Variants must not start until a valid LA TLMM donor source is available.

## 8. PM verdict: GO, GO_WITH_LIMITATIONS, or NO_GO
`NO_GO`

Reason: LE target and relative skeleton are clear, but LA source donor is missing, so an honest LA-to-LE hidden-target conversion experiment cannot be executed.
