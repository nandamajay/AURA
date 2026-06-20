# WCD9378 Post-Monday Usage Policy for Promoted WCD Family Rules

Generated: 2026-06-20

## 1. Which promoted rules can be applied immediately after evidence?
Immediately applicable once Monday evidence package is ingested:
- LE architecture split and lifecycle framing rules.
- LA-to-LE DT normalization checklist.
- Vendor include/API elimination mapping discipline.
- Anti-copy/anti-derivation verifier enforcement.
- PM non-claims vocabulary and lineage requirements.

## 2. Which rules require runtime confirmation?
Require explicit runtime confirmation before behavioral conclusions:
- SDW numeric identity and compatible tuple finalization.
- SoundWire paging/controller behavior decisions.
- Class-H base/version and domain behavior decisions.
- Any reset/re-enumeration behavior beyond LE baseline framework usage.

## 3. Which rules must not be applied to WCD9378?
Must not be applied:
- LA-heavy carryover heuristic that increases downstream-near-copy risk.
- Any rule that treats compile score improvement as runtime proof.
- Any sibling-codec inference rule for WCD9378 SDW identity or Class-H behavior.

## 4. How to avoid copying WCD938x/WCD939x into WCD9378?
- Keep WCD9378 transformations anchored to WCD9378 LA donor semantics, not sibling file text.
- Require anti-copy verifier checks against LA donor and LE references on every iteration.
- Require subsystem lineage notes that explain transformation intent (not file transplant intent).

## 5. How to evaluate A.2 vs A.1 if changes are made?
Evaluate A.2 against A.1 with this minimum package:
- Side-by-side rule-impact diff referencing promoted rule IDs.
- Gate/scorer/verifier delta including vendor-elimination and derivation warning delta.
- Runtime blocker status diff with evidence IDs for every changed blocker.
- PM summary with explicit "what must NOT be claimed" section.

## 6. What evidence is needed before SoundWire, Class-H, or reset changes?
SoundWire:
- dmesg/sysfs identity tuple logs (manufacturer, part, class, version, dev_num).
- Paging traces for addresses above 0xffff and controller-path confirmation.

Class-H:
- Register traces for HPH/Class-H/flyback enable-disable sequences.
- Verified register domain/base evidence from runtime traces.

Reset/runtime recovery:
- Before/after regmap dumps around reset or runtime suspend/resume.
- Failure reproduction logs showing why LE baseline handling is insufficient.

## 7. What PM verdicts are allowed?
Allowed PM verdicts for WCD9378 until runtime blockers close:
- `RFC_STATIC_READY_RUNTIME_BLOCKED`
- `RUNTIME_EVIDENCE_INGESTED_REVIEW_PENDING`
- `PARTIAL_UNBLOCK_WITH_FAIL_CLOSED_REMAINDERS`

Not allowed before runtime closure:
- Any verdict claiming production runtime readiness or upstream-ready playback/capture success.
