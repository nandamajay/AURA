# WCD938X Reviewer Prediction Report

## Predicted reviewer behavior vs available evidence
| Reviewer | Predicted focus | Evidence availability | Assessment |
|---|---|---|---|
| Mark Brown | kcontrol semantics, patch scope, ASoC model hygiene | `INSUFFICIENT_EVIDENCE` for direct `wcd938x` comment text | Medium-confidence projection from WSA evidence and maintainer model |
| Pierre-Louis Bossart | SoundWire lifecycle, PM robustness | `INSUFFICIENT_EVIDENCE` for direct `wcd938x` comment text | Medium-confidence projection from WSA and SoundWire maintainer profile |
| Krzysztof Kozlowski | DT schema split/property correctness | `INSUFFICIENT_EVIDENCE` for direct `wcd938x` comment text | Low-confidence projection |
| Vinod Koul | SoundWire transport conventions | `INSUFFICIENT_EVIDENCE` | Low-confidence projection |
| Bjorn Andersson | Qualcomm integration consistency | `INSUFFICIENT_EVIDENCE` | Low-confidence projection |

## Why confidence is lower than WSA883x
`wcd938x` review corpus in KB currently lacks direct extracted reviewer comment text:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/review_comments.md:3-4`

## Reviewer-survival score
- **63/100**

Rationale:
- Strong architecture alignment signals, but low direct reviewer-text evidence reduces prediction reliability.

Supporting evidence:
- Maintainer models:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/mark_brown.md:10-20`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/pierre_bossart.md:10-19`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/krzysztof_kozlowski.md:9-15`
- WCD review evidence gap:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/review_comments.md:3-4`

