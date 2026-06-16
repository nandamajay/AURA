# Review Failure Patterns

## Pattern catalog
| Pattern | Type | Drivers seen | Effect on review survival |
|---|---|---|---|
| Missing direct reviewer evidence causes low-confidence survival prediction | Qualcomm-wide process gap | wsa884x, wcd938x, lpass_rx_macro, lpass_tx_macro, lpass_va_macro | High negative on prediction reliability |
| Kcontrol semantic mismatch (`put` callback change return) | Maintainer-specific rule with wide impact | wsa883x | High negative; blocks acceptance until fixed |
| Control naming/style mismatch in user-visible controls | Maintainer-specific | wsa883x | Medium negative; causes extra revision |
| Runtime resume path without explicit timeout safety | Maintainer-specific + subsystem safety | wsa883x | Medium-high negative; follow-up robustness patch required |
| Overly broad patch surfaces in early revisions | Qualcomm-wide | wsa883x/wsa884x/wcd938x timeline patterns | Medium negative; increases superseded cycles |

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md:4-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/patch_history.md:4-7`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/patch_history.md:4-8`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/multi_driver_evidence_report.md:6-10`

## Rejected approaches (explicit or inferred)
- Explicit: ALSA control callback semantics not matching maintainer expectation (revised before acceptance).
- Explicit: Control naming/style required correction before acceptance.
- Inferred (timeline evidence): early series organization that required multiple superseding revisions.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa883x/review_comments.md:14-20`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa883x/patch_history.md:14-16`

