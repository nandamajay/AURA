# Family Review Models

## WSA Family (wsa883x, wsa884x)
Model summary:
- High sensitivity to control semantics and naming quality in codec patches.
- SoundWire lifecycle and runtime PM robustness are recurring review focal points.
- Fast convergence possible when small targeted revisions address feedback.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md:4-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/patch_history.md:4-10`

Family-specific review rules (evidence-backed):
1. Validate kcontrol semantics before v1 send.
2. Keep controls/DAPM patches narrow and style-clean.
3. Add PM robustness follow-up quickly if requested.

## WCD Family (wcd938x)
Model summary:
- Long revision timeline indicates higher complexity and larger patch surface.
- Split ownership (core + SDW side) likely demands review in ownership-aligned chunks.
- Direct reviewer comment text currently insufficient in KB for detailed maintainer-personality modeling.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/patch_history.md:4-15`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wcd938x.md:3-8`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/review_comments.md:3-4`

Family-specific review rules (evidence-backed):
1. Expect multi-revision convergence for complex codec series.
2. Split by ownership blocks (DT/core/SDW/control) to reduce review churn.
3. Treat reviewer predictions as low-confidence without direct comment extraction.

## LPASS Macro Family (rx/tx/va)
Model summary:
- Acceptance captured with smaller core patch sets and series-level evolution evidence.
- Direct reviewer-comment evidence is sparse; inference is mostly timeline-driven.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_rx_macro/patch_history.md:3-10`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_tx_macro/patch_history.md:3-10`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_va_macro/patch_history.md:3-10`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/lpass_*_macro/review_comments.md:3-4`

Family-specific review rules (evidence-backed):
1. Keep macro support and routing updates separable.
2. Prioritize architecture consistency over feature breadth in initial series.

## Machine Driver Family
Status: `INSUFFICIENT_EVIDENCE`
- No machine-driver-specific review corpus with comment-level extraction is present in current KB.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/` (no machine-driver review profiles)
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/*/*/README.md`

## SoundWire Driver Family
Status: `PARTIAL_EVIDENCE`
- Explicit SoundWire review evidence exists mainly via `wsa883x` (Pierre) and structural acceptance patterns in WCD/WSA timelines.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/soundwire/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/patch_history.md:4-15`

