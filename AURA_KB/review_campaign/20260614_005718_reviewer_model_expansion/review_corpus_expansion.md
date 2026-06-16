# Review Corpus Expansion

## Scope
Review-learning campaign only (no reconstruction/conversion).
Sources mined:
- `drivers/*/review_comments.md`
- `drivers/*/patch_history.md`
- `lore_links/*.md`
- `accepted_commits/*.md`
- `review_database/*/*/*.md`

Target families coverage:
- WSA family: `wsa883x`, `wsa884x`
- WCD family: `wcd938x`
- LPASS macro family: `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Machine drivers: `INSUFFICIENT_EVIDENCE` in current KB review corpus
- SoundWire drivers: partially represented via WSA/WCD codec+transport review artifacts

## Per-driver review evidence inventory
| Driver | Review comments extracted | Requested changes captured | Rejected approaches captured | Accepted corrections captured | v1->vN evolution captured | Evidence quality |
|---|---|---|---|---|---|---|
| wsa883x | YES | YES | YES | YES | YES (v1->v3) | STRONGEST |
| wsa884x | NO (comment bodies unavailable) | PARTIAL (from revision chain only) | PARTIAL | PARTIAL | YES (v1->v4) | PARTIAL |
| wcd938x | NO (comment bodies unavailable) | PARTIAL (from revision chain only) | PARTIAL | PARTIAL | YES (v1->v9) | PARTIAL |
| lpass_rx_macro | NO | PARTIAL | PARTIAL | PARTIAL | PARTIAL (accepted series observed) | LIMITED |
| lpass_tx_macro | NO | PARTIAL | PARTIAL | PARTIAL | PARTIAL (accepted series observed) | LIMITED |
| lpass_va_macro | NO | PARTIAL | PARTIAL | PARTIAL | PARTIAL (accepted series observed) | LIMITED |

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa883x/review_comments.md:4-20`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/review_comments.md:3-4`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/review_comments.md:3-4`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_rx_macro/review_comments.md:3-4`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_tx_macro/review_comments.md:3-4`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_va_macro/review_comments.md:3-4`

## Requested changes and accepted corrections mined
| Finding | Classification |
|---|---|
| ALSA kcontrol `put` semantics correction required before acceptance | Maintainer-specific + Qualcomm-wide impact |
| Control naming/style correction requested in revision loop | Maintainer-specific |
| Runtime resume timeout robustness requested and merged as follow-up | Maintainer-specific + Qualcomm-wide impact |
| Revision loops (superseded v1/v2/... before acceptance) are normal in all mined families | Qualcomm-wide |
| DT binding and driver evolution happen together over multiple revisions | Qualcomm-wide |
| DAPM/control scope minimization is not uniform across codec families | Family-specific |

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md:4-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/accepted_commits/wsa883x.md:7-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/patch_history.md:4-10`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/patch_history.md:4-15`

## Coverage gaps
- Direct review-comment text is concentrated in `wsa883x`.
- Machine-driver-specific review corpora are not present in current KB.
- Many reviewer/topic buckets contain only `README` placeholders.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/*/*/README.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/multi_driver_evidence_report.md:5-10`

