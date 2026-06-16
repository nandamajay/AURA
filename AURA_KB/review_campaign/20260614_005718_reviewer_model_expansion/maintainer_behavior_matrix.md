# Maintainer Behavior Matrix

| Maintainer/Reviewer | Topics with direct evidence | Common requests | Common objections / risk triggers | Evidence quality | Classification |
|---|---|---|---|---|---|
| Mark Brown | Controls, patch structure (wsa883x) | Correct kcontrol semantics; naming/style cleanup; focused revision deltas | ALSA semantic violations; mixed/unclear patch scope | MEDIUM | Maintainer-specific |
| Pierre-Louis Bossart | Runtime PM, SoundWire callback behavior (wsa883x) | Timeout-safe resume handling; callback condition robustness | Fragile lifecycle assumptions in SDW/PM paths | MEDIUM | Maintainer-specific |
| Krzysztof Kozlowski | DT trend evidence (partial) | Schema consistency and property modeling hygiene | Inconsistent DT schema/property patterns | LOW | Maintainer-specific (partial) |
| Vinod Koul | No direct comment-level evidence in current corpus | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | LOW | Maintainer-specific (insufficient) |
| Bjorn Andersson | No direct comment-level evidence in current corpus | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | LOW | Maintainer-specific (insufficient) |
| Other reviewers | Sparse patch-structure references | Driver-specific observations in later revisions | INSUFFICIENT_EVIDENCE for broader behavior model | LOW | Driver-specific / partial |

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md:4-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/patch_structure/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/soundwire/wsa883x.md:4-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/krzysztof_kozlowski/dt/wsa883x.md:3-6`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/vinod_koul.md:3-8`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/bjorn_andersson.md:3-8`

