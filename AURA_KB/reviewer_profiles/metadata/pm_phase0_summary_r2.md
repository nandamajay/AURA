# PM Phase 0 Summary (R2)

Generated: 2026-06-21T12:41:10Z

Terminology:
- LA = downstream / Linux Android
- LE = upstream / Linux Embedded

## 1. Which P0 reviewers have HIGH confidence profiles?
- Mark Brown: HIGH
- Pierre-Louis Bossart: INSUFFICIENT_DATA
- Krzysztof Kozlowski: HIGH
- Vinod Koul: INSUFFICIENT_DATA

## 2. Which reviewers are LOW_CONFIDENCE or INSUFFICIENT_DATA?
- Pierre-Louis Bossart (INSUFFICIENT_DATA)
- Vinod Koul (INSUFFICIENT_DATA)
- Liam Girdwood (INSUFFICIENT_DATA)
- Bjorn Andersson (LOW_CONFIDENCE)
- Linus Walleij (LOW_CONFIDENCE)
- Rob Herring (INSUFFICIENT_DATA)
- Konrad Dybcio (INSUFFICIENT_DATA)

## 3. What are the top 5 objection patterns per P0 reviewer?
- Mark Brown: \bdon't\b, aux devices, codec do, cover more, dai link
- Pierre-Louis Bossart: \bissue\b, \bneeds?\s+to\b, devid registers, in devid, in devid registers
- Krzysztof Kozlowski: \bfix\b, \bdo\s+not\b, against bindings, dts against, dts against bindings
- Vinod Koul: N/A

## 4. What are the top 5 subsystem rules per P0 subsystem?
- asoc_qcom: \basoc\b, \basoc\b, \bqcom\b, \bqcom\b, dt-binding
- soundwire: \basoc\b, \bqcom\b, dt-binding, \bsoundwire\b, soundwire
- dt_bindings_audio: \basoc\b, \bqcom\b, dt-binding, \bpinctrl\b, \bqcom\b

## 5. What did profile validation show?
- Accepted cases: 5
- Rejected/changes-requested cases: 5
- Overall precision: 0.29
- Overall recall: 0.40
- False positives on accepted: 5
- False negatives on rejected: 3

## 6. Is Phase 0 success criteria met?
- NO

## 7. Is Phase 1 unblocked?
- NO

## 8. What should be improved before Phase 1?
- Increase comment-thread coverage for reviewers still below HIGH confidence.
- Continue reducing acceptance-email and courtesy-signoff leakage into objection signals.
- Add reviewer-specific lexicon tuning for SoundWire and dt-bindings objection language.

Verdict: `PHASE_0_FAILED_RETRY_REQUIRED`
