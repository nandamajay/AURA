# Validated Learning Extraction - wsa883x Forensics

Promotion policy applied: only validated evidence; no assumption that upstream is always superior.

| Finding | Classification | Action | Validation basis |
|---|---|---|---|
| Generic SDW ownership model is the stable upstream direction for WSA family | RULE_REFINEMENT | Refine SoundWire rule text to explicitly include migration from vendor SWR DAPM transport nodes to SDW stream lifecycle callbacks | Downstream SWR path vs upstream SDW callbacks: DS `/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa883x/wsa883x.c:1058-1145`, `:2208-2231`; US `/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c:1356-1366`, `:1404-1408`, `:1717-1728` |
| Runtime PM should be evaluated as a two-step acceptance path (base runtime PM + follow-up robustness fix) | RULE_REFINEMENT | Amend runtime PM rule to encode follow-up hardening as expected review outcome | Review + accepted commit evidence: `/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`, `/AURA_KB/accepted_commits/wsa883x.md:8` |
| Keep codec driver independent from machine runtime channel-map programming when DT/property can own mapping | NEW_PATTERN | Add codec pattern: “de-machine-couple port mapping” | DS machine coupling `/track_b_corpora/audio-kernel-ar/asoc/audio_machine.c:2209-2211`; US DT parse `/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c:1635-1637` |
| DAPM minimalism is valid, but transport control can still be exposed via kcontrols | PATTERN_REFINEMENT | Clarify DAPM rule to distinguish graph minimalism from transport configurability via controls | DS DAPM transport node `/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa883x/wsa883x.c:1256-1269`; US controls `/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c:1306-1321` |
| Mark Brown model should weight control semantics as first-order blocker | MAINTAINER_MODEL_UPDATE | Increase severity ranking of kcontrol semantics in Mark profile | `/AURA_KB/review_database/mark_brown/controls/wsa883x.md:5-12` |
| Pierre model should explicitly include callback condition scrutiny in SDW state flow | MAINTAINER_MODEL_UPDATE | Add “invariant-condition challenge” signal to Pierre profile | `/AURA_KB/review_database/pierre_bossart/soundwire/wsa883x.md:5-6` |
| AURA 6-patch split was not objectively worse; mismatch mostly historical cadence | NO_ACTION_REQUIRED | Keep current split capability; only add historical cadence hint in playbook | AURA split `/.../reconstructed_patch_series.md:8-13`; Lore cadence `/AURA_KB/lore_links/wsa883x.md:3-14` |
| Non-primary reviewer prediction remains low-confidence due to evidence sparsity | NEW_RULE | Add evidence-threshold rule for reviewer simulation confidence tagging | `/.../reviewer_prediction_accuracy.md:8-10`; `/AURA_KB/multi_driver_evidence_report.md:6-10` |

